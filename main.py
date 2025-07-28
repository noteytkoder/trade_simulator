import yaml
import threading
import time
import dash
from dash import html, dcc
import plotly.graph_objs as go
from utils.parser import TableParser
from trading.simulator import TradeSimulator

# Загрузка конфигурации
env_config = yaml.safe_load(open('config.yaml', 'r'))

# TODO: Создать экземпляры TradeSimulator для каждого интервала
# simulators = { '5s': ..., '1m': ..., '1h': ... }

app = dash.Dash(__name__)
server = app.server

app.layout = html.Div([
    html.H1("Симулятор торговли"),
    # --- Панель параметров
    html.Div(id='controls', children=[
        # TODO: input для balance, threshold, fee, выбор интервала, кнопки start/stop/reset
    ]),
    # --- Таблица сделок
    html.Div(id='trade-log'),
    # --- График баланса
    dcc.Graph(id='balance-graph'),
    dcc.Interval(id='poll-interval', interval=env_config['poll_interval'] * 1000, n_intervals=0),
])

# Колбэк на интервал опроса
def update_data(n):
    # TODO: вызвать парсер, затем simulator.process_tick, затем обновить интерфейс
    pass

# TODO: зарегистрировать callback(`poll-interval`, обновление таблицы и графика)

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8055)