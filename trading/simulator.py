from datetime import datetime

class TradeSimulator:
    def __init__(
        self, start_balance: float, entry_threshold: float,
        fee_pct: float, interval: str
    ):
        # TODO: инициализация переменных (balance, btc, buy_price, log и т.д.)
        pass

    def process_tick(self, tick: dict):
        """
        Обрабатывает новую "тик"-информацию:
          - tick['actual_price']
          - tick['predictions'][interval]
        Выполняет buy/sell логику.
        """
        # TODO: если нет позиции и прогноз выше threshold -> buy
        # TODO: если в позиции и достигнут профит или сменился знак прогноза -> sell
        pass

    def buy(self, price: float, timestamp: str):
        # TODO: расчёт комиссии, количества BTC, запись в лог
        pass

    def sell(self, price: float, timestamp: str):
        # TODO: расчёт комиссии, обновление баланса, запись в лог
        pass

    def get_trade_log(self) -> list:
        # TODO: вернуть список словарей с записями сделок
        pass

    def get_balance_series(self) -> list:
        # TODO: вернуть список (timestamp, balance) для графика
        pass