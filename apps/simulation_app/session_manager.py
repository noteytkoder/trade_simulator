import yaml
import dash
from dash import Dash, html, dcc, dash_table
from dash.dependencies import Input, Output, State
from flask_httpauth import HTTPBasicAuth
from apps.simulation_app.simulation_manager import SimulationManager
from utils.logger import setup_logger
from utils.auth import verify_credentials
import logging

logger = setup_logger('session_manager')

class SessionManagerDashboard:
    def __init__(self):
        self.config = yaml.safe_load(open('config.yaml', 'r'))
        self.env = self.config.get('env', 'prod')
        self.simulation_port = self.config['ports'][self.env]['simulation']
        self.manager = SimulationManager()
        # logger.info(f"SessionManager использует SimulationManager, экземпляр: {id(self.manager)}, simulations: {id(self.manager.simulations)}")
        logger.setLevel(getattr(logging, self.config.get('log_level', 'INFO')))
        self.app = Dash(__name__, external_stylesheets=[
            'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
        ], suppress_callback_exceptions=True)
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

    def create_layout(self):
        return html.Div([
            html.H1("Менеджер сессий симуляции", className='text-3xl font-bold mb-6 text-center text-gray-800'),
            html.Div(className='mb-6 bg-white p-4 rounded-lg shadow-md', children=[
                html.H3("Создать новую сессию", className='text-xl font-semibold mb-4'),
                html.Div(className='flex flex-wrap gap-4 items-center', children=[
                    html.Label("Баланс:", className='font-medium'),
                    dcc.Input(id='new-balance-input', type='number', value=self.config['start_balance'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Порог входа (%):", className='font-medium'),
                    dcc.Input(id='new-entry-threshold-input', type='number', value=self.config['entry_threshold'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Порог выхода (%):", className='font-medium'),
                    dcc.Input(id='new-exit-threshold-input', type='number', value=self.config['exit_threshold'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Комиссия (%):", className='font-medium'),
                    dcc.Input(id='new-fee-input', type='number', value=self.config['fee_pct'], className='border rounded px-2 py-1 w-32'),
                    html.Label("MAE стоп включен:", className='font-medium'),
                    dcc.Checklist(id='new-mae-enabled', options=[{'label': '', 'value': 'enabled'}], value=['enabled'] if self.config['mae_stop_enabled'] else [], className='border rounded px-2 py-1'),
                    html.Label("MAE порог:", className='font-medium'),
                    dcc.Input(id='new-mae-threshold', type='number', value=self.config['mae_stop_threshold'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Стоп-лосс %:", className='font-medium'),
                    dcc.Input(id='new-sl-pct', type='number', value=self.config['stop_loss_pct'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Интервал:", className='font-medium'),
                    dcc.Dropdown(
                        id='new-interval-dropdown',
                        options=[
                            {'label': '5 секунд', 'value': '5s'},
                            {'label': '1 минута', 'value': '1m'}
                        ],
                        value='5s',
                        className='border rounded px-2 py-1 w-32'
                    ),
                    html.Button("Создать сессию", id='create-session-button', className='bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600')
                ])
            ]),
            html.H3("Активные сессии", className='text-xl font-semibold mb-4'),
            dcc.Interval(id='interval-component', interval=5*1000, n_intervals=0),
            html.Div(id='sessions-table-container'),
            dcc.Store(id='action-trigger')
        ])

    def register_callbacks(self):
        @self.app.callback(
            Output('sessions-table-container', 'children'),
            [Input('interval-component', 'n_intervals')]
        )
        def update_sessions_table(n_intervals):
            sessions = self.manager.list_sessions()
            logger.info(f"Обновление таблицы сессий: найдено {len(sessions)} сессий. Экземпляр: {id(self.manager)}, simulations: {id(self.manager.simulations)}")
            data = [
                {
                    'interval': s['interval'],
                    'session_id': s['session_id'],
                    'balance': f"{s['balance']:.4f}",
                    'btc': f"{s['btc']:.6f}",
                    'profit': f"{s['profit']:.4f}",
                    'accuracy': f"{s['accuracy']:.2f}%",
                    'running': 'Запущена' if s['running'] else 'Остановлена',
                    'paused': 'На паузе' if s['paused'] else 'Активна',
                    'auto_paused': 'Да' if s['auto_paused'] else 'Нет',
                    'start_time': s['start_time'],
                    'entry_threshold': f"{s['entry_threshold']:.6f}%",
                    'exit_threshold': f"{s['exit_threshold']:.6f}%",
                    'fee_pct': f"{s['fee_pct']:.2f}%",
                    'mae_stop_enabled': 'Да' if s['mae_stop_enabled'] else 'Нет',
                    'mae_stop_threshold': f"{s['mae_stop_threshold']:.6f}",
                    'stop_loss_pct': f"{s['stop_loss_pct']:.6f}%",
                    'last_mae': f"{s['last_mae']:.4f}" if s['last_mae'] is not None else "...",
                    'view_dashboard': f"[Открыть дашборд](http://185.5.248.212:{self.simulation_port}?session_id={s['session_id']})",
                    'view_log': f"[Открыть лог](http://185.5.248.212:{self.config['ports'][self.env]['logs']}/logs/simulation_{s['session_id']}.csv)",
                    'stop_action': '[Остановить]' if s['running'] else '—',
                    'pause_action': '[Пауза]' if s['running'] and not s['paused'] else '[Возобновить]' if s['running'] and s['paused'] else '—'
                } for s in sessions
            ]
            table = dash_table.DataTable(
                id='sessions-table',
                columns=[
                    {'name': 'Интервал', 'id': 'interval'},
                    {'name': 'ID сессии', 'id': 'session_id'},
                    {'name': 'Баланс', 'id': 'balance'},
                    {'name': 'BTC', 'id': 'btc'},
                    {'name': 'Прибыль', 'id': 'profit'},
                    {'name': 'Точность', 'id': 'accuracy'},
                    {'name': 'Статус', 'id': 'running'},
                    {'name': 'Пауза', 'id': 'paused'},
                    {'name': 'Авто-пауза', 'id': 'auto_paused'},
                    # {'name': 'Время старта', 'id': 'start_time'},
                    # {'name': 'Порог входа', 'id': 'entry_threshold'},
                    # {'name': 'Порог выхода', 'id': 'exit_threshold'},
                    # {'name': 'Комиссия', 'id': 'fee_pct'},
                    # {'name': 'MAE стоп', 'id': 'mae_stop_enabled'},
                    # {'name': 'MAE порог', 'id': 'mae_stop_threshold'},
                    # {'name': 'Стоп-лосс %', 'id': 'stop_loss_pct'},
                    # {'name': 'Последний MAE', 'id': 'last_mae'},
                    {'name': 'Дашборд', 'id': 'view_dashboard', 'type': 'text', 'presentation': 'markdown'},
                    {'name': 'Лог', 'id': 'view_log', 'type': 'text', 'presentation': 'markdown'},
                    {'name': 'Стоп', 'id': 'stop_action', 'type': 'text', 'presentation': 'markdown'},
                    {'name': 'Пауза', 'id': 'pause_action', 'type': 'text', 'presentation': 'markdown'}
                ],
                data=data,
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'padding': '5px'},
                style_header={'fontWeight': 'bold', 'backgroundColor': '#f3f4f6'},
                style_data_conditional=[
                    {
                        'if': {'column_id': 'stop_action'},
                        'backgroundColor': 'red', 'color': 'white', 'cursor': 'pointer', 'textAlign': 'center', 'fontWeight': 'bold'
                    },
                    {
                        'if': {'column_id': 'pause_action'},
                        'backgroundColor': 'blue', 'color': 'white', 'cursor': 'pointer', 'textAlign': 'center', 'fontWeight': 'bold'
                    }
                ],
                sort_action='native'
            )
            return table

        @self.app.callback(
            Output('create-session-button', 'n_clicks'),
            [Input('create-session-button', 'n_clicks')],
            [State('new-interval-dropdown', 'value'), State('new-balance-input', 'value'),
             State('new-entry-threshold-input', 'value'), State('new-exit-threshold-input', 'value'),
             State('new-fee-input', 'value'), State('new-mae-enabled', 'value'),
             State('new-mae-threshold', 'value'), State('new-sl-pct', 'value')]
        )
        def create_session(n_clicks, interval, balance, entry, exit_t, fee, mae_enabled, mae_threshold, sl_pct):
            if n_clicks > 0:
                mae_enabled = 'enabled' in (mae_enabled or [])
                session_id = self.manager.start_simulation(interval, balance, entry, exit_t, fee, mae_enabled, mae_threshold, sl_pct)
                logger.info(f"Создана сессия {session_id} через форму. Экземпляр: {id(self.manager)}, simulations: {id(self.manager.simulations)}")
                return 0
            return n_clicks

        @self.app.callback(
            Output('action-trigger', 'data'),
            [Input('sessions-table', 'active_cell')],
            [State('sessions-table', 'data')]
        )
        def handle_table_actions(active_cell, table_data):
            if not active_cell:
                return None
            row = active_cell['row']
            col = active_cell['column_id']
            session_id = table_data[row]['session_id']
            if col == 'stop_action':
                interval = session_id.split('_')[0]
                self.manager.stop_simulation(interval, session_id)
                logger.info(f"Сессия {session_id} остановлена через таблицу. Экземпляр: {id(self.manager)}, simulations: {id(self.manager.simulations)}")
                return {'action': 'stop', 'session_id': session_id}
            elif col == 'pause_action':
                interval = session_id.split('_')[0]
                sess_data = self.manager.simulations.get(interval, {}).get(session_id, {})
                current_paused = sess_data.get('paused', False)
                self.manager.pause_simulation(interval, session_id, not current_paused)
                logger.info(f"Сессия {session_id} {'приостановлена' if not current_paused else 'возобновлена'} через таблицу. Экземпляр: {id(self.manager)}, simulations: {id(self.manager.simulations)}")
                return {'action': 'pause', 'session_id': session_id}
            return None

    def run(self):
        port = self.config['ports'][self.env]['session_manager']
        logger.info(f"Запуск session_manager на порту {port}")
        self.app.run(host='0.0.0.0', port=port, debug=False)
