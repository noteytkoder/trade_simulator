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
                    html.Label("Краш-пауза:", className='font-medium'),
                    dcc.Checklist(id='new-crash-enabled', options=[{'label': '', 'value': 'enabled'}], value=['enabled'] if self.config['market_crash_halt']['enabled'] else [], className='border rounded px-2 py-1'),
                    html.Label("Порог падения (%):", className='font-medium'),
                    dcc.Input(id='new-crash-threshold', type='number', value=self.config['market_crash_halt']['threshold_pct'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Период наблюдения (мин):", className='font-medium'),
                    dcc.Input(id='new-crash-lookback', type='number', value=self.config['market_crash_halt']['lookback_minutes'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Режим восстановления:", className='font-medium'),
                    dcc.Dropdown(
                        id='new-crash-recovery-mode',
                        options=[
                            {'label': 'Восстановление цены', 'value': 'price_recovery'},
                            {'label': 'Стабильные бары', 'value': 'stable_bars'}
                        ],
                        value=self.config['market_crash_halt']['recovery_mode'],
                        className='border rounded px-2 py-1 w-32'
                    ),
                    html.Label("Порог восстановления (%):", className='font-medium'),
                    dcc.Input(id='new-recovery-threshold', type='number', value=self.config['market_crash_halt']['recovery_threshold_pct'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Кол-во стабильных баров:", className='font-medium'),
                    dcc.Input(id='new-stable-bars-count', type='number', value=self.config['market_crash_halt']['stable_bars_count'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Порог стабильности (%):", className='font-medium'),
                    dcc.Input(id='new-stable-bar-threshold', type='number', value=self.config['market_crash_halt']['stable_bar_threshold_pct'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Интервал:", className='font-medium'),
                    dcc.Dropdown(
                        id='new-interval-dropdown',
                        options=[
                            {'label': '5 секунд', 'value': '5s'},
                            {'label': '1 минута', 'value': '1m'},
                            {'label': '1 час', 'value': '1h'}
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
            ip = "127.0.0.1"
            sessions = self.manager.list_sessions()
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
                    'crash_paused': 'Да' if s['crash_paused'] else 'Нет',
                    'start_time': s['start_time'],
                    'entry_threshold': f"{s['entry_threshold']:.6f}%",
                    'exit_threshold': f"{s['exit_threshold']:.6f}%",
                    'fee_pct': f"{s['fee_pct']:.2f}%",
                    'mae_stop_enabled': 'Да' if s['mae_stop_enabled'] else 'Нет',
                    'mae_stop_threshold': f"{s['mae_stop_threshold']:.6f}",
                    'stop_loss_pct': f"{s['stop_loss_pct']:.6f}%",
                    'crash_halt_enabled': 'Да' if s['crash_halt_enabled'] else 'Нет',
                    'last_mae': f"{s['last_mae']:.4f}" if s['last_mae'] is not None else "...",
                    'view_dashboard': f"[Открыть дашборд](http://{ip}:{self.simulation_port}?session_id={s['session_id']})",
                    'view_log': f"[Открыть лог](http://{ip}:{self.config['ports'][self.env]['logs']}/logs/simulation_{s['session_id']}.csv)",
                    'stop_action': '[Остановить]' if s['running'] else '—',
                    'pause_action': '[Пауза]' if s['running'] and not s['paused'] else '[Возобновить]' if s['running'] and s['paused'] else '—',
                    'reset_crash_action': '[Сбросить краш]' if s['crash_paused'] else '—'
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
                    {'name': 'Краш-пауза', 'id': 'crash_paused'},
                    {'name': 'Дашборд', 'id': 'view_dashboard', 'type': 'text', 'presentation': 'markdown'},
                    {'name': 'Лог', 'id': 'view_log', 'type': 'text', 'presentation': 'markdown'},
                    {'name': 'Стоп', 'id': 'stop_action', 'type': 'text', 'presentation': 'markdown'},
                    {'name': 'Пауза', 'id': 'pause_action', 'type': 'text', 'presentation': 'markdown'},
                    {'name': 'Сброс краша', 'id': 'reset_crash_action', 'type': 'text', 'presentation': 'markdown'}
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
                    },
                    {
                        'if': {'column_id': 'reset_crash_action'},
                        'backgroundColor': 'green', 'color': 'white', 'cursor': 'pointer', 'textAlign': 'center', 'fontWeight': 'bold'
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
             State('new-mae-threshold', 'value'), State('new-sl-pct', 'value'),
             State('new-crash-enabled', 'value'), State('new-crash-threshold', 'value'),
             State('new-crash-lookback', 'value'), State('new-crash-recovery-mode', 'value'),
             State('new-recovery-threshold', 'value'), State('new-stable-bars-count', 'value'),
             State('new-stable-bar-threshold', 'value')]
        )
        def create_session(n_clicks, interval, balance, entry, exit_t, fee, mae_enabled, mae_threshold, sl_pct,
                          crash_enabled, crash_threshold, crash_lookback, crash_recovery_mode,
                          recovery_threshold, stable_bars_count, stable_bar_threshold):
            if n_clicks > 0:
                mae_enabled = 'enabled' in (mae_enabled or [])
                crash_enabled = 'enabled' in (crash_enabled or [])
                session_id = self.manager.start_simulation(
                    interval, balance, entry, exit_t, fee, mae_enabled, mae_threshold, sl_pct,
                    crash_enabled, crash_threshold, crash_lookback, crash_recovery_mode,
                    recovery_threshold, stable_bars_count, stable_bar_threshold
                )
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
            elif col == 'reset_crash_action':
                interval = session_id.split('_')[0]
                sim = self.manager.get_simulator(interval, session_id)
                if sim and sim.crash_paused:
                    sim.crash_paused = False
                    sim.auto_paused = False
                    sim.stable_bars = 0
                    sim.lowest_price_after_crash = None
                    logger.info(f"Краш-пауза сброшена для сессии {session_id}")
                return {'action': 'reset_crash', 'session_id': session_id}
            return None

    def run(self):
        port = self.config['ports'][self.env]['session_manager']
        logger.info(f"Запуск session_manager на порту {port}")
        self.app.run(host='0.0.0.0', port=port, debug=False)