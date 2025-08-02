import yaml
import dash
from dash import Dash, html, dcc
from dash.dependencies import Input, Output, State
from apps.simulation_app.simulation_manager import SimulationManager
from utils.logger import setup_logger

logger = setup_logger('simulation_dashboard')

class TradingDashboard:
    def __init__(self):
        self.config = yaml.safe_load(open('config.yaml', 'r'))
        self.manager = SimulationManager()
        self.app = Dash(__name__, external_stylesheets=[
            'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
        ], suppress_callback_exceptions=True)
        self.setup_layout()
        self.register_callbacks()

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
            dcc.Interval(id='poll-interval', interval=2000, disabled=False)
        ])

    def register_callbacks(self):
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

            # При загрузке страницы проверяем статус
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
            [Output('btc-amount', 'children'),
             Output('current-balance', 'children'),
             Output('total-profit', 'children'),
             Output('balance-graph', 'figure')],
            [Input('poll-interval', 'n_intervals')],
            [State('interval-dropdown', 'value')]
        )
        def update_dashboard(n_intervals, interval):
            sim = self.manager.get_simulator(interval)
            if not sim:
                return "BTC: 0.0", "Баланс: 0.0 USDT", "Прибыль: 0.0 USDT", {'data': [], 'layout': {'title': 'Нет данных'}}

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
                f"BTC: {sim.get_current_btc():.6f}",
                f"Баланс: {sim.get_current_balance():.2f} USDT",
                f"Прибыль: {sim.get_total_profit():.2f} USDT",
                figure
            )

    def run(self, port=8050):
        self.app.run(host='0.0.0.0', port=port, debug=False)
