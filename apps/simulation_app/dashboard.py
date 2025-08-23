import yaml
import dash
from dash import Dash, html, dcc
from dash.dependencies import Input, Output, State
from flask_httpauth import HTTPBasicAuth
from apps.simulation_app.simulation_manager import SimulationManager
from utils.logger import setup_logger
from utils.auth import verify_credentials, update_password
from urllib.parse import parse_qs
import logging
from datetime import datetime

logger = setup_logger('simulation_dashboard')

class TradingDashboard:
    def __init__(self):
        self.config = yaml.safe_load(open('config.yaml', 'r'))
        self.env = self.config.get('env', 'prod')
        self.session_manager_port = self.config['ports'][self.env]['session_manager']
        self.auth_config = yaml.safe_load(open('auth.yaml', 'r'))
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
            dcc.Location(id='url', refresh=False),
            html.Div(id='page-content', children=self.create_main_layout())
        ])

    def create_main_layout(self):
        return html.Div([
            html.H1("Симулятор торговли", className='text-3xl font-bold mb-6 text-center text-gray-800'),
            html.A('Назад к менеджеру сессий', href=f"http://185.5.248.212:{self.session_manager_port}", className='text-blue-500 hover:underline mb-4 inline-block'),
            html.Div(id='session-params', className='mb-6 bg-white p-4 rounded-lg shadow-md', children=[
                html.H3("Параметры сессии", className='text-xl font-semibold mb-4'),
                html.P(id='session-interval', children="Интервал: N/A", className='text-gray-700'),
                html.P(id='session-balance', children="Начальный баланс: N/A", className='text-gray-700'),
                html.P(id='session-entry', children="Порог входа: N/A", className='text-gray-700'),
                html.P(id='session-exit', children="Порог выхода: N/A", className='text-gray-700'),
                html.P(id='session-fee', children="Комиссия: N/A", className='text-gray-700'),
                html.Hr(className='my-4'),  # Разделитель
                html.P(id='session-price', children="Текущий курс BTCUSDT: 0.0", className='text-gray-700'),
                html.P(id='session-btc', children="BTC: 0.0", className='text-gray-700'),
                html.P(id='session-current-balance', children="Баланс: 0.0", className='text-gray-700'),
                html.P(id='session-profit', children="Прибыль: 0.0", className='text-gray-700'),
                html.P(id='session-accuracy', children="Точность прогнозов: 0.0%", className='text-gray-700'),
                html.P(id='session-mae', children="MAE 10min: ...", className='text-gray-700'),
            ]),
            html.Div(id='error-message', children="", className='text-red-500 mb-4'),
            dcc.Graph(id='balance-graph'),
            dcc.Graph(id='profit-graph'),
            dcc.Graph(id='accuracy-graph'),
            dcc.Graph(id='mae-graph'),
            html.Button("Пауза/Возобновить", id='pause-button', className='bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600', disabled=True),
            dcc.Interval(id='interval-component', interval=2*1000, n_intervals=0)
        ])

    def register_callbacks(self):
        @self.app.callback(
            [
                Output('session-price', 'children'),
                Output('session-btc', 'children'),
                Output('session-current-balance', 'children'),
                Output('session-profit', 'children'),
                Output('session-accuracy', 'children'),
                Output('session-interval', 'children'),
                Output('session-balance', 'children'),
                Output('session-entry', 'children'),
                Output('session-exit', 'children'),
                Output('session-fee', 'children'),
                Output('session-mae', 'children'),
                Output('balance-graph', 'figure'),
                Output('profit-graph', 'figure'),
                Output('accuracy-graph', 'figure'),
                Output('mae-graph', 'figure'),
                Output('pause-button', 'disabled'),
                Output('error-message', 'children')
            ],
            [Input('interval-component', 'n_intervals'), Input('url', 'search')]
        )
        def update_dashboard(n_intervals, search):
            query_params = parse_qs(search.lstrip('?'))
            session_id = query_params.get('session_id', [None])[0]
            logger.info(f"Попытка подгрузки сессии {session_id} из URL {search}. Экземпляр SimulationManager: {id(self.manager)}, simulations: {id(self.manager.simulations)}")
            current_price = self.manager.get_current_price() or 0.0

            if session_id is None:
                logger.warning("session_id не найден в URL, показываем дефолт")
                return (
                    f"Текущий курс BTCUSDT: {current_price:.4f}",
                    "BTC: 0.0",
                    "Баланс: 0.0",
                    "Прибыль: 0.0",
                    "Точность прогнозов: 0.0%",
                    "Интервал: N/A",
                    "Начальный баланс: N/A",
                    "Порог входа: N/A",
                    "Порог выхода: N/A",
                    "Комиссия: N/A",
                    "MAE 10min: ...",
                    {'data': [], 'layout': {'title': 'Нет данных'}},
                    {'data': [], 'layout': {'title': 'Нет данных'}},
                    {'data': [], 'layout': {'title': 'Нет данных'}},
                    {'data': [], 'layout': {'title': 'Нет данных'}},
                    True,
                    "Выберите сессию"
                )

            interval = session_id.split('_')[0]
            sim = self.manager.get_simulator(interval, session_id)
            if not sim:
                logger.warning(f"Сессия {session_id} не найдена в памяти, показываем дефолт")
                return (
                    f"Текущий курс BTCUSDT: {current_price:.4f}",
                    "BTC: 0.0",
                    "Баланс: 0.0",
                    "Прибыль: 0.0",
                    "Точность прогнозов: 0.0%",
                    f"Интервал: {interval}",
                    "Начальный баланс: N/A",
                    "Порог входа: N/A",
                    "Порог выхода: N/A",
                    "Комиссия: N/A",
                    "MAE 10min: ...",
                    {'data': [], 'layout': {'title': f'Сессия {session_id} не найдена'}},
                    {'data': [], 'layout': {'title': f'Сессия {session_id} не найдена'}},
                    {'data': [], 'layout': {'title': f'Сессия {session_id} не найдена'}},
                    {'data': [], 'layout': {'title': f'Сессия {session_id} не найдена'}},
                    True,
                    "Сессия не найдена в памяти"
                )

            logger.info(f"Сессия {session_id} подгружена успешно: параметры {sim.metadata}, данные {len(sim.trade_log)} записей")
            balance_series = sim.get_balance_series()
            balance_series = sorted(balance_series, key=lambda t: datetime.strptime(t[0], '%Y-%m-%d %H:%M:%S'))
            profit_series = sim.get_profit_series()
            accuracy_series = sim.get_accuracy_series()
            mae_series = sim.get_mae_series()
            
            balance_fig = {
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
                    'title': {
                        'text': f'График баланса',
                        'font': {'size': 20, 'family': 'Arial', 'weight': 'bold'},
                        #'x': 0.5,  # Центрировать заголовок
                        'xanchor': 'center'
                    },
                    'xaxis': {'title': 'Время'},
                    'yaxis': {'title': 'Баланс'},
                    'height': 400,
                    'margin': {'t': 50}  # Увеличить отступ сверху для заголовка
                }
            }

            profit_fig = {
                'data': [
                    {
                        'x': [t for t, p in profit_series],
                        'y': [p for t, p in profit_series],
                        'type': 'bar',
                        'name': 'Прибыль',
                        'marker': {'color': ['green' if p > 0 else 'red' for t, p in profit_series]}
                    }
                ],
                'layout': {
                    'title': {
                        'text': f'График прибыли/убытков',
                        'font': {'size': 20, 'family': 'Arial', 'weight': 'bold'},
                        #'x': 0.5,
                        'xanchor': 'center'
                    },
                    'xaxis': {'title': 'Время'},
                    'yaxis': {'title': 'Прибыль'},
                    'height': 300,
                    'margin': {'t': 50}
                }
            }

            accuracy_fig = {
                'data': [
                    {
                        'x': [t for t, a in accuracy_series],
                        'y': [a for t, a in accuracy_series],
                        'type': 'line',
                        'name': 'Точность',
                        'line': {'color': '#ff7f0e'}
                    }
                ],
                'layout': {
                    'title': {
                        'text': f'График точности прогнозов (%)',
                        'font': {'size': 20, 'family': 'Arial', 'weight': 'bold'},
                        'x': 0.5,
                        'xanchor': 'center'
                    },
                    'xaxis': {'title': 'Время'},
                    'yaxis': {'title': 'Точность (%)'},
                    'height': 300,
                    'margin': {'t': 50}
                }
            }

            mae_fig = {
                'data': [
                    {
                        'x': [t for t, m in mae_series],
                        'y': [m for t, m in mae_series],
                        'type': 'line',
                        'name': 'MAE',
                        'line': {'color': '#2ca02c'}
                    }
                ],
                'layout': {
                    'title': {
                        'text': f'График MAE за 10 мин',
                        'font': {'size': 20, 'family': 'Arial', 'weight': 'bold'},
                        'x': 0.5,
                        'xanchor': 'center'
                    },
                    'xaxis': {'title': 'Время'},
                    'yaxis': {'title': 'MAE'},
                    'height': 300,
                    'margin': {'t': 50}
                }
            }

            return (
                f"Текущий курс BTCUSDT: {current_price:.4f}",
                f"BTC: {sim.get_current_btc():.6f}",
                f"Баланс: {sim.get_current_balance():.4f}",
                f"Прибыль: {sim.get_total_profit():.6f}",
                f"Точность прогнозов: {sim.get_prediction_accuracy():.2f}%",
                f"Интервал: {sim.interval}",
                f"Начальный баланс: {sim.metadata['start_balance']:.6f}",
                f"Порог входа: {sim.entry_threshold:.6f}%",
                f"Порог выхода: {sim.exit_threshold:.6f}%",
                f"Комиссия: {sim.fee_pct:.6f}%",
                f"MAE 10min: {sim.get_last_mae():.4f}" if sim.get_last_mae() is not None else "MAE 10min: ...",
                balance_fig,
                profit_fig,
                accuracy_fig,
                mae_fig,
                False,
                ""
            )

        @self.app.callback(
            Output('pause-button', 'children'),
            [Input('pause-button', 'n_clicks'), Input('url', 'search')],
            [State('pause-button', 'children')]
        )
        def control_simulation(n_clicks, search, current_label):
            if n_clicks is None or n_clicks == 0:
                return current_label
            query_params = parse_qs(search.lstrip('?'))
            session_id = query_params.get('session_id', [None])[0]
            if session_id:
                interval = session_id.split('_')[0]
                sess_data = self.manager.simulations.get(interval, {}).get(session_id, {})
                current_paused = sess_data.get('paused', False)
                self.manager.pause_simulation(interval, session_id, not current_paused)
                return "Возобновить" if current_paused else "Пауза"
            return current_label

    def run(self):
        port = self.config['ports'][self.env]['simulation']
        logger.info(f"Запуск dashboard на порту {port}")
        self.app.run(host='0.0.0.0', port=port, debug=False)
