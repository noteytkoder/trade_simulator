import yaml
import dash
from dash import Dash, html, dcc, dash_table
from dash.dependencies import Input, Output, State
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
        self.app = Dash(
            __name__,
            external_stylesheets=[
                'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
            ],
            suppress_callback_exceptions=True
        )
        self.logged_in = False
        self.app.layout = self.create_layout()
        self.register_callbacks()

    def reload_config(self):
        """Перечитать конфиг с диска."""
        try:
            with open('config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Ошибка чтения конфига: {e}")
            return {}

    def update_config(self, key: str, value: any):
        """Безопасно обновить конфиг, не теряя другие ключи."""
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

            current[keys[-1]] = value  # Исправлено: keys вместо keys[-1]

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
            html.Div(id='page-content', children=self.create_login_layout())
        ])

    def create_login_layout(self):
        return html.Div([
            html.H1("Авторизация", className='text-3xl font-bold mb-6 text-center text-gray-800'),
            html.Div(className='max-w-md mx-auto bg-white p-6 rounded-lg shadow-md', children=[
                html.Label("Логин:", className='font-medium'),
                dcc.Input(id='username-input', type='text', value='', className='border rounded px-2 py-1 w-full mb-4'),
                html.Label("Пароль:", className='font-medium'),
                dcc.Input(id='password-input', type='password', value='', className='border rounded px-2 py-1 w-full mb-4'),
                html.Button('Войти', id='login-button', n_clicks=0, className='bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600'),
                html.P(id='login-error', className='text-red-500 mt-2')
            ])
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
        return html.Div([
            html.H1(f"Содержимое файла: {filename}", className='text-3xl font-bold mb-6 text-center text-gray-800'),
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

    def create_total_layout(self):
        """Создаёт layout для страницы /logtotal с общей статистикой."""
        total_trades = 0
        total_profit = 0.0
        total_correct_predictions = 0
        total_predictions = 0
        files_processed = 0

        try:
            for filename in os.listdir('simulations'):
                if filename.endswith('.csv'):
                    filepath = os.path.join('simulations', filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        lines_for_table = [line for line in lines if not line.startswith('#') and line.strip()]
                        if not lines_for_table:
                            continue
                        reader = csv.DictReader(lines_for_table)
                        for row in reader:
                            total_trades += 1
                            if row.get('profit'):
                                try:
                                    total_profit += float(row['profit'])
                                except ValueError:
                                    pass
                            if row.get('prediction_accuracy') == 'True':
                                total_correct_predictions += 1
                            if row.get('prediction_accuracy') in ['True', 'False']:
                                total_predictions += 1
                    files_processed += 1

            accuracy = (total_correct_predictions / total_predictions * 100) if total_predictions > 0 else 0.0

            return html.Div([
                html.H1("Общая статистика логов", className='text-3xl font-bold mb-6 text-center text-gray-800'),
                html.A('Назад к списку файлов', href='/', className='text-blue-500 hover:underline mb-4 inline-block', target='_self'),
                html.Div(className='bg-white p-4 rounded-lg shadow-md', children=[
                    html.H3("Сводка", className='text-xl font-semibold mb-4'),
                    html.P(f"Обработано файлов: {files_processed}", className='text-gray-700'),
                    html.P(f"Всего сделок: {total_trades}", className='text-gray-700'),
                    html.P(f"Общая прибыль: {total_profit:.2f} USDT", className='text-gray-700'),
                    html.P(f"Точность прогнозов: {accuracy:.2f}%", className='text-gray-700')
                ])
            ])
        except Exception as e:
            logger.error(f"Ошибка при формировании статистики /logtotal: {e}")
            return html.P(f"Ошибка при загрузке статистики: {e}", className='text-red-500')

    def register_callbacks(self):
        @self.app.callback(
            Output('page-content', 'children'),
            [Input('url', 'pathname')],
            [State('username-input', 'value'),
             State('password-input', 'value')]
        )
        def update_page_content(pathname, username, password):
            if pathname == '/':
                if not self.logged_in:
                    return self.create_login_layout()
                return self.create_logs_layout()
            elif pathname.startswith('/logs/'):
                if not self.logged_in:
                    return self.create_login_layout()
                filename = urllib.parse.unquote(pathname[len('/logs/'):])
                return self.create_file_content_layout(filename)
            elif pathname == '/logtotal':
                if not self.logged_in:
                    return self.create_login_layout()
                return self.create_total_layout()
            return self.create_login_layout()

        @self.app.callback(
            Output('login-error', 'children'),
            [Input('login-button', 'n_clicks')],
            [State('username-input', 'value'),
             State('password-input', 'value')]
        )
        def login(n_clicks, username, password):
            if n_clicks > 0:
                if verify_credentials(username, password):
                    self.logged_in = True
                    logger.info("Успешная авторизация")
                    return ""
                logger.info("Неудачная попытка авторизации")
                return "Неверный логин или пароль"
            return ""

        @self.app.callback(
            Output('file-table-container', 'children'),
            [Input('log-update-interval', 'n_intervals'),
             Input('log-interval-dropdown', 'value')]
        )
        def update_file_table(n_intervals, logs_interval):
            if not self.logged_in:
                return html.P("Требуется авторизация", className='text-red-500')

            try:
                files = [
                    {'filename': f, 'size': os.path.getsize(os.path.join('simulations', f)),
                     'mtime': datetime.fromtimestamp(os.path.getmtime(os.path.join('simulations', f)), tz=ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')}
                    for f in os.listdir('simulations') if f.endswith('.csv') and logs_interval in f
                ]
                files.sort(key=lambda x: x['mtime'], reverse=True)

                return dash_table.DataTable(
                    id='file-table',
                    columns=[
                        {'name': 'Файл', 'id': 'filename', 'type': 'text', 'presentation': 'markdown'},
                        {'name': 'Размер (байт)', 'id': 'size', 'type': 'numeric'},
                        {'name': 'Дата изменения', 'id': 'mtime', 'type': 'text'}
                    ],
                    data=[{
                        'filename': f"[**{row['filename']}**](/logs/{urllib.parse.quote(row['filename'])})",
                        'size': row['size'],
                        'mtime': row['mtime']
                    } for row in files],
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'left', 'padding': '5px'},
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f3f4f6'},
                    style_data_conditional=[
                        {'if': {'column_id': 'filename'}, 'color': 'blue', 'textDecoration': 'none'}
                    ],
                    sort_action='native',
                    filter_action='native',
                    page_action='native',
                    page_size=10
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении таблицы файлов: {e}")
                return html.P(f"Ошибка при загрузке списка файлов: {e}", className='text-red-500')

        @self.app.callback(
            Output('file-content', 'children'),
            [Input('url', 'pathname')]
        )
        def update_file_content(pathname):
            if not pathname.startswith('/logs/'):
                return html.Div()

            filename = urllib.parse.unquote(pathname[len('/logs/'):])
            filepath = os.path.join('simulations', filename)
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
                        page_size=self.reload_config().get('ui', {}).get('logs_page_size', 25)
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
            return dash.no_update

        @self.app.callback(
            Output('url', 'pathname'),
            [Input('file-table', 'active_cell')],
            [State('file-table', 'data')]
        )
        def navigate_to_file(active_cell, file_data):
            if active_cell and file_data:
                row_index = active_cell['row']
                filename = file_data[row_index]['filename']
                return f"/logs/{urllib.parse.quote(filename)}"
            return dash.no_update

        @self.app.callback(
            Output('log-interval-dropdown', 'value'),
            [Input('log-interval-dropdown', 'value')]
        )
        def on_interval_change(logs_interval):
            if logs_interval:
                self.update_config('ui.logs_interval', logs_interval)
            return logs_interval

        @self.app.callback(
            Output('page-size-dropdown', 'value'),
            [Input('page-size-dropdown', 'value')]
        )
        def on_page_size_change(page_size):
            if page_size:
                self.update_config('ui.logs_page_size', page_size)
            return page_size

    def run(self, port=8055):
        self.app.run(host='0.0.0.0', port=port, debug=False)