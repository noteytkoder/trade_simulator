import yaml
import dash
from dash import Dash, html, dcc
from dash.dependencies import Input, Output, State
from trading.simulator import TradeSimulator
from utils.parser import TableParser
from utils.logger import setup_logger
import atexit

logger = setup_logger('simulation_dashboard')

class TradingDashboard:
    def __init__(self):
        self.config = yaml.safe_load(open('config.yaml', 'r'))
        self.auth = (self.config['auth']['username'], self.config['auth']['password'])
        self.simulators = {
            '5s': TradeSimulator(
                self.config['start_balance'],
                self.config['entry_threshold'],
                self.config['exit_threshold'],
                self.config['fee_pct'],
                '5s'
            ),
            '1m': TradeSimulator(
                self.config['start_balance'],
                self.config['entry_threshold'],
                self.config['exit_threshold'],
                self.config['fee_pct'],
                '1m'
            ),
            '1h': TradeSimulator(
                self.config['start_balance'],
                self.config['entry_threshold'],
                self.config['exit_threshold'],
                self.config['fee_pct'],
                '1h'
            )
        }
        self.app = Dash(__name__, external_stylesheets=[
            'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
        ])
        self.running_intervals = {'5s': False, '1m': False, '1h': False}
        self.setup_layout()
        self.register_callbacks()
        atexit.register(self.save_all_sessions)

    def save_all_sessions(self):
        for interval, simulator in self.simulators.items():
            if self.running_intervals[interval]:
                simulator.save_session()
                logger.info(f"Сохранена сессия для интервала {interval} при завершении")

    def update_config(self, key: str, value: any):
        try:
            with open('config.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
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

    def setup_layout(self):
        self.app.layout = html.Div([
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
                html.P(id='btc-amount', children="BTC: 0.0", className='text-gray-700'),
                html.P(id='current-balance', children="Баланс: 0.0 USDT", className='text-gray-700'),
                html.P(id='total-profit', children="Прибыль: 0.0 USDT", className='text-gray-700'),
            ]),
            dcc.Graph(id='balance-graph', config={'displayModeBar': True, 'scrollZoom': True}),
            dcc.Interval(id='poll-interval', interval=1000, disabled=True),
            dcc.Store(id='running-state', data=self.running_intervals)
        ])

    def register_callbacks(self):
        @self.app.callback(
            [Output('poll-interval', 'disabled'),
             Output('poll-interval', 'interval'),
             Output('status-indicator', 'children'),
             Output('running-state', 'data')],
            [Input('start-button', 'n_clicks'), Input('stop-button', 'n_clicks')],
            [State('interval-dropdown', 'value'), State('running-state', 'data')]
        )
        def toggle_polling(start_clicks, stop_clicks, interval, running_state):
            self.running_intervals = running_state
            if start_clicks > stop_clicks:
                if interval not in self.simulators:
                    self.simulators[interval] = TradeSimulator(
                        self.config['start_balance'],
                        self.config['entry_threshold'],
                        self.config['exit_threshold'],
                        self.config['fee_pct'],
                        interval
                    )
                self.running_intervals[interval] = True
                poll_interval = self.config['poll_intervals'].get(interval, 5) * 1000
                logger.info(f"Запуск опроса данных для интервала {interval} с частотой {poll_interval} мс")
                return False, poll_interval, html.Span("🟢 Активно", className='text-green-500 font-bold'), self.running_intervals
            else:
                self.running_intervals[interval] = False
                logger.info(f"Остановка опроса данных для интервала {interval}")
                return True, 1000, html.Span("🔴 Остановлено", className='text-red-500 font-bold'), self.running_intervals

        @self.app.callback(
            [Output('btc-amount', 'children'),
             Output('current-balance', 'children'),
             Output('total-profit', 'children'),
             Output('balance-graph', 'figure')],
            [Input('poll-interval', 'n_intervals'),
             Input('start-button', 'n_clicks')],
            [State('interval-dropdown', 'value'),
             State('balance-input', 'value'),
             State('entry-threshold-input', 'value'),
             State('exit-threshold-input', 'value'),
             State('fee-input', 'value')]
        )
        def update_dashboard(n_intervals, start_clicks, interval, balance, entry_threshold, exit_threshold, fee):
            ctx = dash.callback_context
            if ctx.triggered_id == 'start-button':
                self.simulators[interval] = TradeSimulator(
                    balance or self.config['start_balance'],
                    entry_threshold or self.config['entry_threshold'],
                    exit_threshold or self.config['exit_threshold'],
                    fee or self.config['fee_pct'],
                    interval
                )
                logger.info(f"Запуск симулятора для интервала {interval}")

            if n_intervals is None or not self.running_intervals[interval]:
                return (
                    f"BTC: {0:.8f}",
                    f"Баланс: {0:.2f} USDT",
                    f"Прибыль: {0:.2f} USDT",
                    {'data': [], 'layout': {'title': f'Баланс ({interval})', 'xaxis': {'title': 'Время'}, 'yaxis': {'title': 'Баланс (USDT)'}}}
                )

            try:
                endpoint = self.config['endpoints']['five_sec'] if interval == '5s' else self.config['endpoints']['minute_hour']
                html_content = TableParser.fetch(endpoint, self.auth)
                tick = TableParser.parse(html_content, interval)
                logger.debug(f"Получен tick: {tick}")
                self.simulators[interval].process_tick(tick)

                balance_series = self.simulators[interval].get_balance_series()
                logger.debug(f"Обновление balance_series: {balance_series}")
                figure = {
                    'data': [
                        {
                            'x': [t[0] for t in balance_series],
                            'y': [t[1] for t in balance_series],
                            'type': 'line',
                            'name': 'Баланс',
                            'line': {'color': '#1f77b4'}
                        },
                        {
                            'x': [t[0] for t in balance_series],
                            'y': [sum(log.get('profit', 0) for log in self.simulators[interval].get_trade_log()[:i+1]) for i in range(len(balance_series))],
                            'type': 'line',
                            'name': 'Прибыль',
                            'line': {'color': '#ff7f0e', 'dash': 'dash'}
                        }
                    ],
                    'layout': {
                        'title': f'Баланс и прибыль ({interval})',
                        'xaxis': {'title': 'Время', 'tickangle': 45},
                        'yaxis': {'title': 'USDT'},
                        'showlegend': True,
                        'margin': {'b': 150}
                    }
                }
                return (
                    f"BTC: {self.simulators[interval].get_current_btc():.6f}",
                    f"Баланс: {self.simulators[interval].get_current_balance():.2f} USDT",
                    f"Прибыль: {self.simulators[interval].get_total_profit():.2f} USDT",
                    figure
                )
            except Exception as e:
                logger.error(f"Ошибка обновления дашборда: {e}")
                return (
                    f"BTC: {self.simulators[interval].get_current_btc():.6f}",
                    f"Баланс: {self.simulators[interval].get_current_balance():.2f} USDT",
                    f"Прибыль: {self.simulators[interval].get_total_profit():.2f} USDT",
                    {'data': [], 'layout': {'title': f'Баланс ({interval})', 'xaxis': {'title': 'Время'}, 'yaxis': {'title': 'Баланс (USDT)'}}}
                )

        @self.app.callback(
            Output('dummy-output', 'children'),
            [Input('interval-dropdown', 'value')]
        )
        def update_config_values(main_interval):
            if main_interval:
                self.update_config('ui.default_interval', main_interval)
            return ""

    def run(self, port=8060):
        self.app.run(host='0.0.0.0', port=port, debug=False)