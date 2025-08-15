import yaml
import dash
from dash import Dash, html, dcc, dash_table, no_update
from dash.dependencies import Input, Output, State
from flask_httpauth import HTTPBasicAuth
from utils.logger import setup_logger
from utils.auth import verify_credentials
import os
import csv
from datetime import datetime
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo  # Python <3.9
import urllib.parse
import tempfile
import shutil

logger = setup_logger('logs_dashboard')

class LogsDashboard:
    def __init__(self):
        self.config = yaml.safe_load(open('config.yaml', 'r'))
        self.env = self.config.get('env', 'prod')
        self.app = Dash(
            __name__,
            external_stylesheets=[
                'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
            ],
            suppress_callback_exceptions=True
        )
        self.auth = HTTPBasicAuth()
        self.app.layout = self.create_layout()
        self.register_callbacks()
        self.register_auth()

    def register_auth(self):
        @self.auth.verify_password
        def verify_password(username, password):
            return verify_credentials(username, password)

        @self.app.server.before_request
        def require_auth():
            return self.auth.login_required(lambda: None)()

    def reload_config(self):
        try:
            with open('config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Ошибка чтения конфига: {e}")
            return {}

    def update_config(self, key: str, value: any):
        try:
            if os.path.exists('config.yaml'):
                with open('config.yaml', 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            keys = key.split('.')
            current = config
            for k in keys[:-1]:
                if k not in current or not isinstance(current[k], dict):
                    current[k] = {}
                current = current[k]

            if current.get(keys[-1]) == value:
                return

            current[keys[-1]] = value

            tmp_fd, tmp_path = tempfile.mkstemp()
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as tmp_file:
                yaml.safe_dump(config, tmp_file, allow_unicode=True, sort_keys=False)
            shutil.move(tmp_path, 'config.yaml')

            logger.info(f"Обновлён конфиг: {key} = {value}")
        except Exception as e:
            logger.error(f"Ошибка обновления конфига: {e}")

    def create_layout(self):
        return html.Div([
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='url-store'),
            dcc.Store(id='page-size-store', data=self.reload_config().get('ui', {}).get('logs_page_size', 25)),  # Добавляем Store для page_size
            html.Div(id='page-content', children=self.create_logs_layout())
        ])

    def create_logs_layout(self):
        config = self.reload_config()
        logs_interval = config.get('ui', {}).get('logs_interval', '5s')
        page_size = config.get('ui', {}).get('logs_page_size', 25)
        return html.Div([
            html.H1("Логи торговли", className='text-3xl font-bold mb-6 text-center text-gray-800'),
            html.Label("Интервал логов:", className='font-medium mr-2'),
            dcc.Dropdown(
                id='log-interval-dropdown',
                options=[
                    {'label': '5 секунд', 'value': '5s'},
                    {'label': '1 минута', 'value': '1m'},
                    {'label': '1 час', 'value': '1h'}
                ],
                value=logs_interval,
                className='w-48 mb-4'
            ),
            html.Label("Записей на странице:", className='font-medium mr-2'),
            dcc.Dropdown(
                id='page-size-dropdown',
                options=[{'label': str(i), 'value': i} for i in [10, 25, 50, 100]],
                value=page_size,
                className='w-32 mb-4'
            ),
            html.Div(id='file-table-container', className='bg-white p-4 rounded-lg shadow-md mb-4'),
            dcc.Interval(id='log-update-interval', interval=5000, disabled=False)
        ])

    def create_file_content_layout(self, filename):
        config = self.reload_config()
        page_size = config.get('ui', {}).get('logs_page_size', 25)
        # Извлекаем session_id из filename (simulation_{session_id}.csv)
        session_id = filename.replace('simulation_', '').replace('.csv', '')
        return html.Div([
            html.H1(f"Содержимое файла: {filename} (сессия {session_id})", className='text-3xl font-bold mb-6 text-center text-gray-800'),
            html.A('Назад к списку файлов', href='/', className='text-blue-500 hover:underline mb-4 inline-block', target='_self'),
            html.Button('Скачать CSV', id='download-button', n_clicks=0, className='bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 mb-4'),
            dcc.Download(id='download-file'),
            html.Label("Записей на странице:", className='font-medium mr-2'),
            dcc.Dropdown(
                id='page-size-dropdown',
                options=[{'label': str(i), 'value': i} for i in [10, 25, 50, 100]],
                value=page_size,
                className='w-32 mb-4'
            ),
            html.Div(id='file-content')
        ])

    def register_callbacks(self):
        @self.app.callback(
            Output('page-content', 'children'),
            [Input('url', 'pathname'), Input('url-store', 'data')]
        )
        def update_page_content(pathname, data):
            if pathname == '/':
                return self.create_logs_layout()
            elif pathname.startswith('/logs/'):
                filename = urllib.parse.unquote(pathname[len('/logs/'):])
                return self.create_file_content_layout(filename)
            return html.P("Страница не найдена", className='text-red-500')

        @self.app.callback(
            Output('file-table-container', 'children'),
            [Input('log-update-interval', 'n_intervals'), Input('log-interval-dropdown', 'value')]
        )
        def update_file_table(n_intervals, logs_interval):
            files = []
            folder = 'simulations'
            if os.path.exists(folder):
                files = [f for f in os.listdir(folder) if f.endswith('.csv')]
                files.sort(key=lambda f: os.path.getmtime(os.path.join(folder, f)), reverse=True)

            if not files:
                return html.P("Нет файлов логов", className='text-gray-500')

            data = []
            for filename in files:
                filepath = os.path.join(folder, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                session_id = filename.replace('simulation_', '').replace('.csv', '')
                interval = session_id.split('_')[0]
                data.append({
                    'filename': filename,
                    'session_id': session_id,
                    'interval': interval,
                    'modified': file_time,
                    'link': f"[Открыть](/logs/{urllib.parse.quote(filename)})"
                })

            table = dash_table.DataTable(
                id='file-table',
                columns=[
                    {'name': 'Имя файла', 'id': 'filename'},
                    {'name': 'ID сессии', 'id': 'session_id'},
                    {'name': 'Интервал', 'id': 'interval'},
                    {'name': 'Дата изменения', 'id': 'modified'},
                    {'name': 'Ссылка', 'id': 'link', 'presentation': 'markdown'}
                ],
                data=data,
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'padding': '5px'},
                style_header={'fontWeight': 'bold', 'backgroundColor': '#f3f4f6'},
                sort_action='native'
            )
            return table

        @self.app.callback(
            Output('file-content', 'children'),
            [Input('url', 'pathname'), Input('page-size-store', 'data')]
        )
        def load_log_content(pathname, page_size):
            if not pathname.startswith('/logs/'):
                return no_update
            filename = urllib.parse.unquote(pathname[len('/logs/'):])
            filepath = os.path.join('simulations', filename)
            if not os.path.exists(filepath):
                return html.P(f"Файл {filename} не найден", className='text-red-500')

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    metadata = {}
                    for line in lines:
                        if line.startswith('#'):
                            key, value = line[1:].strip().split(':', 1)
                            metadata[key.strip()] = value.strip()
                    lines_for_table = [line for line in lines if not line.startswith('#') and line.strip()]
                    reader = csv.DictReader(lines_for_table)
                    log_data = [row for row in reader if row]

                    meta_table = html.Table([
                        html.Tr([html.Th("Параметр"), html.Th("Значение")])
                    ] + [
                        html.Tr([html.Td(k), html.Td(v)]) for k, v in metadata.items()
                    ], className='table-auto mb-4 border-collapse border border-gray-300')

                    columns = [
                        {'name': 'Время', 'id': 'timestamp'},
                        {'name': 'Тип', 'id': 'type'},
                        {'name': 'Цена', 'id': 'price', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Количество', 'id': 'amount', 'type': 'numeric', 'format': {'specifier': '.6f'}},
                        {'name': 'Комиссия', 'id': 'fee', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Баланс', 'id': 'balance', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Прибыль', 'id': 'profit', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Факт. цена', 'id': 'actual_price', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Прогноз', 'id': 'predicted_price', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Прогноз %', 'id': 'predicted_change_pct', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Причина', 'id': 'reason'},
                        {'name': 'Точность', 'id': 'prediction_accuracy'}
                    ]

                    content_table = dash_table.DataTable(
                        id='trade-table',
                        data=log_data,
                        columns=columns,
                        style_table={'overflowX': 'auto'},
                        style_cell={'textAlign': 'left', 'padding': '5px'},
                        style_header={'fontWeight': 'bold', 'backgroundColor': '#f3f4f6'},
                        style_data_conditional=[
                            {'if': {'column_id': 'profit', 'filter_query': '{profit} > 0'}, 'color': 'green'},
                            {'if': {'column_id': 'profit', 'filter_query': '{profit} < 0'}, 'color': 'red'},
                            {'if': {'column_id': 'prediction_accuracy', 'filter_query': '{prediction_accuracy} = "True"'}, 'color': 'green'},
                            {'if': {'column_id': 'prediction_accuracy', 'filter_query': '{prediction_accuracy} = "False"'}, 'color': 'red'}
                        ],
                        sort_action='native',
                        filter_action='native',
                        page_action='native',
                        page_size=page_size or 25  # Используем page_size из page-size-store
                    )

                    return html.Div([
                        html.H4("Параметры сессии", className="text-xl font-semibold mb-2"),
                        meta_table,
                        html.H4("История сделок", className="text-xl font-semibold mb-2 mt-4"),
                        content_table
                    ])

            except Exception as e:
                logger.error(f"Ошибка чтения файла {filename}: {e}")
                return html.P(f"Ошибка при чтении файла: {e}", className='text-red-500')

        @self.app.callback(
            Output('download-file', 'data'),
            [Input('download-button', 'n_clicks')],
            [State('url', 'pathname')]
        )
        def download_file(n_clicks, pathname):
            if n_clicks > 0 and pathname.startswith('/logs/'):
                filename = urllib.parse.unquote(pathname[len('/logs/'):])
                filepath = os.path.join('simulations', filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return dcc.send_string(content, filename)
                except Exception as e:
                    logger.error(f"Ошибка при скачивании файла {filename}: {e}")
            return no_update

        @self.app.callback(
            Output('log-interval-dropdown', 'value'),
            [Input('log-interval-dropdown', 'value')]
        )
        def on_interval_change(logs_interval):
            if logs_interval:
                self.update_config('ui.logs_interval', logs_interval)
            return logs_interval

        @self.app.callback(
            [Output('page-size-store', 'data'),
             Output('page-size-dropdown', 'value')],
            [Input('page-size-dropdown', 'value')]
        )
        def on_page_size_change(page_size):
            if page_size:
                self.update_config('ui.logs_page_size', page_size)
                return page_size, page_size
            return no_update, no_update

    def run(self):
        port = self.config['ports'][self.env]['logs']
        logger.info(f"Запуск LogsDashboard на порту {port}")
        self.app.run(host='0.0.0.0', port=port, debug=False)