import yaml
import dash
from dash import Dash, html, dcc, dash_table
from dash.dependencies import Input, Output
from utils.logger import setup_logger
import os
import csv
from datetime import datetime
from zoneinfo import ZoneInfo
import urllib.parse

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
        self.logs_layout = self.create_logs_layout()
        self.setup_routes()
        self.register_callbacks()

    def reload_config(self):
        try:
            with open('config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Ошибка чтения конфига: {e}")
            return {}

    def update_config(self, key: str, value: any):
        try:
            with open('config.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            keys = key.split('.')
            current = config
            for k in keys[:-1]:
                current = current.setdefault(k, {})
            current[keys[-1]] = value
            with open('config.yaml', 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True)
            logger.info(f"Обновлён конфиг: {key} = {value}")
        except Exception as e:
            logger.error(f"Ошибка обновления конфига: {e}")

    def create_logs_layout(self):
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
                className='w-48 mb-4'
            ),
            html.Label("Записей на странице:", className='font-medium mr-2'),
            dcc.Dropdown(
                id='page-size-dropdown',
                options=[{'label': str(i), 'value': i} for i in [10, 25, 50, 100]],
                className='w-32 mb-4'
            ),
            html.Div(id='file-table-container', className='bg-white p-4 rounded-lg shadow-md mb-4'),
            dcc.Interval(id='log-update-interval', interval=5000, disabled=False)
        ])

    def create_file_content_layout(self, filename):
        return html.Div([
            html.H1(f"Содержимое файла: {filename}", className='text-3xl font-bold mb-6 text-center text-gray-800'),
            html.A('Назад к списку файлов', href='/', className='text-blue-500 hover:underline mb-4 inline-block'),
            html.Label("Записей на странице:", className='font-medium mr-2'),
            dcc.Dropdown(
                id='page-size-dropdown',
                options=[{'label': str(i), 'value': i} for i in [10, 25, 50, 100]],
                className='w-32 mb-4'
            ),
            html.Div(id='file-content-container', className='bg-white p-4 rounded-lg shadow-md')
        ])

    def setup_routes(self):
        self.app.layout = html.Div([
            dcc.Location(id='url', refresh=False),
            html.Div(id='page-content', className='container mx-auto p-4')
        ])

    def register_callbacks(self):
        @self.app.callback(
            Output('page-content', 'children'),
            [Input('url', 'pathname')]
        )
        def display_page(pathname):
            config = self.reload_config()
            logs_interval = config.get('ui', {}).get('logs_interval', '5s')
            page_size = config.get('ui', {}).get('logs_page_size', 25)

            if pathname == '/':
                layout = self.logs_layout
                layout.children[2].value = logs_interval
                layout.children[4].value = page_size
                return layout
            elif pathname.startswith('/logs/'):
                filename = urllib.parse.unquote(pathname[len('/logs/'):])
                layout = self.create_file_content_layout(filename)
                layout.children[3].value = page_size
                return layout
            return self.logs_layout

        @self.app.callback(
            Output('file-table-container', 'children'),
            [Input('log-update-interval', 'n_intervals'),
             Input('log-interval-dropdown', 'value'),
             Input('page-size-dropdown', 'value')]
        )
        def update_file_list(n_intervals, interval, page_size):
            config = self.reload_config()
            interval = interval or config.get('ui', {}).get('logs_interval', '5s')
            page_size = page_size or config.get('ui', {}).get('logs_page_size', 25)

            def read_metadata(file_path):
                metadata = {}
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('#'):
                            parts = line[1:].strip().split(':', 1)
                            if len(parts) == 2:
                                key, value = parts
                                metadata[key.strip()] = value.strip()
                        elif line.strip() == '':
                            break
                return metadata

            try:
                files = [
                    f for f in os.listdir('simulations')
                    if f.endswith(f'_{interval}.csv') and os.path.isfile(os.path.join('simulations', f))
                ]
                file_data = []
                for f in files:
                    path = os.path.join('simulations', f)
                    meta = read_metadata(path)
                    file_data.append({
                        'filename': f,
                        'created': datetime.fromtimestamp(os.path.getctime(path), tz=ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S'),
                        'interval': meta.get('interval', ''),
                        'balance': meta.get('start_balance', ''),
                        'thresholds': f"{meta.get('entry_threshold', '')} / {meta.get('exit_threshold', '')}",
                        'fee': meta.get('fee_pct', '')
                    })

                file_columns = [
                    {'name': 'Имя файла', 'id': 'filename'},
                    {'name': 'Создано', 'id': 'created'},
                    {'name': 'Интервал', 'id': 'interval'},
                    {'name': 'Баланс', 'id': 'balance'},
                    {'name': 'Пороги', 'id': 'thresholds'},
                    {'name': 'Комиссия', 'id': 'fee'}
                ]

                file_table = dash_table.DataTable(
                    id='file-table',
                    data=file_data,
                    columns=file_columns,
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'left', 'padding': '5px'},
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f3f4f6'},
                    style_data_conditional=[
                        {
                            'if': {'column_id': 'filename'},
                            'textDecoration': 'underline',
                            'color': '#3B82F6',
                            'cursor': 'pointer'
                        }
                    ],
                    tooltip_data=[
                        {
                            'filename': {'value': f'Кликните для просмотра логов: /logs/{urllib.parse.quote(row["filename"])}', 'type': 'markdown'}
                        } for row in file_data
                    ],
                    tooltip_delay=0,
                    tooltip_duration=None,
                    sort_action='native',
                    page_action='native',
                    page_size=page_size
                )
                return file_table
            except Exception as e:
                logger.error(f"Ошибка отображения списка файлов: {e}")
                return html.P(f"Ошибка при загрузке списка файлов: {e}", className='text-red-500')

        @self.app.callback(
            Output('file-content-container', 'children'),
            [Input('url', 'pathname'),
             Input('page-size-dropdown', 'value')]
        )
        def update_file_content(pathname, page_size):
            config = self.reload_config()
            page_size = page_size or config.get('ui', {}).get('logs_page_size', 25)

            if pathname.startswith('/logs/'):
                filename = urllib.parse.unquote(pathname[len('/logs/'):])
                filepath = os.path.join('simulations', filename)
                try:
                    metadata = {}
                    lines_for_table = []
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('#'):
                                key_value = line[1:].strip().split(':', 1)
                                if len(key_value) == 2:
                                    key, value = key_value
                                    metadata[key.strip()] = value.strip()
                            elif line.strip() == "":
                                break
                        lines_for_table = [line for line in f if not line.startswith('#') and line.strip()]

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
                        {'name': 'Прибыль', 'id': 'profit', 'type': 'numeric', 'format': {'specifier': '.2f'}}
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
                            {'if': {'column_id': 'profit', 'filter_query': '{profit} < 0'}, 'color': 'red'}
                        ],
                        sort_action='native',
                        filter_action='native',
                        page_action='native',
                        page_size=page_size
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

            return html.Div()

        @self.app.callback(
            Output('url', 'pathname'),
            [Input('file-table', 'active_cell')],
            [dash.dependencies.State('file-table', 'data')]
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
