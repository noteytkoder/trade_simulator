import yaml
import dash
from dash import Dash, html, dcc
from dash.dependencies import Input, Output, State
from apps.simulation_app.simulation_manager import SimulationManager
from utils.logger import setup_logger
from utils.auth import verify_credentials, update_password

logger = setup_logger('simulation_dashboard')

class TradingDashboard:
    def __init__(self):
        self.config = yaml.safe_load(open('config.yaml', 'r'))
        self.auth_config = yaml.safe_load(open('auth.yaml', 'r'))
        self.manager = SimulationManager()
        self.app = Dash(__name__, external_stylesheets=[
            'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
        ], suppress_callback_exceptions=True)
        self.logged_in = False
        self.app.layout = self.create_layout()
        self.register_callbacks()

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

    def create_main_layout(self):
        return html.Div([
            html.H1("Симулятор торговли", className='text-3xl font-bold mb-6 text-center text-gray-800'),
            html.Div(id='controls', className='mb-6 bg-white p-4 rounded-lg shadow-md', children=[
                html.Div(className='flex flex-wrap gap-4 items-center', children=[
                    html.Label("Баланс (USDT):", className='font-medium'),
                    dcc.Input(id='balance-input', type='number', value=self.config['start_balance'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Порог входа (%):", className='font-medium'),
                    dcc.Input(id='entry-threshold-input', type='number', value=self.config['entry_threshold'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Порог выхода (%):", className='font-medium'),
                    dcc.Input(id='exit-threshold-input', type='number', value=self.config['exit_threshold'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Комиссия (%):", className='font-medium'),
                    dcc.Input(id='fee-input', type='number', value=self.config['fee_pct'], className='border rounded px-2 py-1 w-32'),
                    html.Label("Интервал:", className='font-medium'),
                    dcc.Dropdown(
                        id='interval-dropdown',
                        options=[
                            {'label': '5 секунд', 'value': '5s'},
                            {'label': '1 минута', 'value': '1m'},
                            {'label': '1 час', 'value': '1h'}
                        ],
                        value=self.config.get('ui', {}).get('default_interval', '1m'),
                        className='w-48'
                    ),
                    html.Button('Старт', id='start-button', n_clicks=0, className='bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600'),
                    html.Button('Стоп', id='stop-button', n_clicks=0, className='bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600'),
                    html.Span(id='status-indicator', className='ml-4')
                ])
            ]),
            html.Div(id='stats', className='bg-white p-4 rounded-lg shadow-md mb-6', children=[
                html.H3("Статистика сессии", className='text-xl font-semibold mb-4'),
                html.P(id='current-price', children="Текущий курс BTCUSDT: 0.0", className='text-gray-700'),
                html.P(id='btc-amount', children="BTC: 0.0", className='text-gray-700'),
                html.P(id='current-balance', children="Баланс: 0.0 USDT", className='text-gray-700'),
                html.P(id='total-profit', children="Прибыль: 0.0 USDT", className='text-gray-700'),
                html.P(id='prediction-accuracy', children="Точность прогнозов: 0.0%", className='text-gray-700'),
            ]),
            dcc.Graph(id='balance-graph', config={'displayModeBar': True, 'scrollZoom': True}),
            dcc.Interval(id='poll-interval', interval=2000, disabled=False),
            html.Button('Сменить пароль', id='change-password-button', n_clicks=0, className='bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 mt-4'),
            html.Div(id='password-modal', style={'display': 'none'}, className='fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center', children=[
                html.Div(className='bg-white p-6 rounded-lg shadow-md', children=[
                    html.H3("Смена пароля", className='text-xl font-semibold mb-4'),
                    html.Label("Новый пароль:", className='font-medium'),
                    dcc.Input(id='new-password-input', type='password', value='', className='border rounded px-2 py-1 w-full mb-4'),
                    html.Button('Подтвердить', id='confirm-password-button', n_clicks=0, className='bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600'),
                    html.Button('Отмена', id='cancel-password-button', n_clicks=0, className='bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600 ml-2'),
                    html.P(id='password-error', className='text-red-500 mt-2')
                ])
            ])
        ])

    def register_callbacks(self):
        @self.app.callback(
            Output('page-content', 'children'),
            [Input('login-button', 'n_clicks')],
            [State('username-input', 'value'),
             State('password-input', 'value')]
        )
        def handle_login(n_clicks, username, password):
            if n_clicks > 0:
                if verify_credentials(username, password):
                    self.logged_in = True
                    logger.info("Успешная авторизация")
                    return self.create_main_layout()
                else:
                    logger.warning("Неудачная попытка авторизации")
                    return html.Div([
                        self.create_login_layout(),
                        html.P("Неверный логин или пароль", className='text-red-500 mt-2')
                    ])
            return self.create_login_layout()

        @self.app.callback(
            Output('password-modal', 'style'),
            [Input('change-password-button', 'n_clicks'),
             Input('cancel-password-button', 'n_clicks')],
            [State('password-modal', 'style')]
        )
        def toggle_password_modal(change_n_clicks, cancel_n_clicks, current_style):
            ctx = dash.callback_context
            if ctx.triggered_id == 'change-password-button' and change_n_clicks > 0:
                return {'display': 'flex'}
            elif ctx.triggered_id == 'cancel-password-button' and cancel_n_clicks > 0:
                return {'display': 'none'}
            return current_style

        @self.app.callback(
            Output('password-error', 'children'),
            [Input('confirm-password-button', 'n_clicks')],
            [State('new-password-input', 'value')]
        )
        def handle_password_change(n_clicks, new_password):
            if n_clicks > 0:
                if new_password and len(new_password) >= 6:
                    if update_password(new_password):
                        return "Пароль успешно изменен"
                    return "Ошибка при смене пароля"
                return "Пароль должен быть не короче 6 символов"
            return ""

        @self.app.callback(
            Output('status-indicator', 'children'),
            [Input('start-button', 'n_clicks'), Input('stop-button', 'n_clicks')],
            [State('interval-dropdown', 'value'), State('balance-input', 'value'),
             State('entry-threshold-input', 'value'), State('exit-threshold-input', 'value'),
             State('fee-input', 'value')]
        )
        def control_simulation(start_clicks, stop_clicks, interval, balance, entry, exit_t, fee):
            ctx = dash.callback_context
            trigger = ctx.triggered_id if ctx.triggered_id else None

            if trigger is None:
                sim_info = self.manager.simulations.get(interval)
                if sim_info and sim_info.get("running"):
                    return html.Span("🟢 Активно", className='text-green-500 font-bold')
                return html.Span("⚪ Ожидание", className='text-gray-500 font-bold')

            if trigger == "start-button":
                self.manager.start_simulation(interval, balance, entry, exit_t, fee)
                return html.Span("🟢 Активно", className='text-green-500 font-bold')

            if trigger == "stop-button":
                self.manager.stop_simulation(interval)
                return html.Span("🔴 Остановлено", className='text-red-500 font-bold')

            return html.Span("⚪ Ожидание", className='text-gray-500 font-bold')

        @self.app.callback(
            [Output('current-price', 'children'),
             Output('btc-amount', 'children'),
             Output('current-balance', 'children'),
             Output('total-profit', 'children'),
             Output('prediction-accuracy', 'children'),
             Output('balance-graph', 'figure')],
            [Input('poll-interval', 'n_intervals')],
            [State('interval-dropdown', 'value')]
        )
        def update_dashboard(n_intervals, interval):
            if not self.logged_in:
                return (
                    "Текущий курс BTCUSDT: 0.0",
                    "BTC: 0.0",
                    "Баланс: 0.0 USDT",
                    "Прибыль: 0.0 USDT",
                    "Точность прогнозов: 0.0%",
                    {'data': [], 'layout': {'title': 'Нет данных'}}
                )

            sim = self.manager.get_simulator(interval)
            current_price = self.manager.get_current_price() or 0.0
            if not sim:
                return (
                    f"Текущий курс BTCUSDT: {current_price:.2f}",
                    "BTC: 0.0",
                    "Баланс: 0.0 USDT",
                    "Прибыль: 0.0 USDT",
                    "Точность прогнозов: 0.0%",
                    {'data': [], 'layout': {'title': 'Нет данных'}}
                )

            balance_series = sim.get_balance_series()
            figure = {
                'data': [
                    {
                        'x': [t[0] for t in balance_series],
                        'y': [t[1] for t in balance_series],
                        'type': 'line',
                        'name': 'Баланс',
                        'line': {'color': '#1f77b4'}
                    }
                ],
                'layout': {
                    'title': f'Баланс ({interval})',
                    'xaxis': {'title': 'Время'},
                    'yaxis': {'title': 'USDT'}
                }
            }
            return (
                f"Текущий курс BTCUSDT: {current_price:.2f}",
                f"BTC: {sim.get_current_btc():.6f}",
                f"Баланс: {sim.get_current_balance():.2f} USDT",
                f"Прибыль: {sim.get_total_profit():.2f} USDT",
                f"Точность прогнозов: {sim.get_prediction_accuracy():.2f}%",
                figure
            )

    def run(self, port=8050):
        self.app.run(host='0.0.0.0', port=port, debug=False)