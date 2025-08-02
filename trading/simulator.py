from datetime import datetime
from typing import List, Dict, Tuple
from utils.logger import setup_logger
from utils.csv_writer import save_to_csv
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo  # Python <3.9

import os

logger = setup_logger('simulator')

class TradeSimulator:
    def __init__(
        self, start_balance: float, entry_threshold: float,
        exit_threshold: float, fee_pct: float, interval: str
    ):
        self.balance = start_balance
        self.btc = 0.0
        self.buy_price = 0.0
        self.fee_pct = fee_pct / 100
        self.entry_threshold = entry_threshold / 100
        self.exit_threshold = exit_threshold / 100
        self.interval = interval
        self.trade_log = []
        self.balance_series = [(datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S'), start_balance)]
        self.start_time = datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d_%H-%M-%S')
        self.metadata = {
            'start_balance': start_balance,
            'entry_threshold': entry_threshold,
            'exit_threshold': exit_threshold,
            'fee_pct': fee_pct,
            'interval': interval,
            'start_time': self.start_time
        }
        logger.info(f"Инициализация симулятора ({interval}): баланс={start_balance}, entry={entry_threshold}%, exit={exit_threshold}%, fee={fee_pct}%")

    def process_tick(self, tick: Dict):
        actual_price = tick['actual_price']
        prediction = tick['predictions'].get(self.interval)
        if not prediction:
            return

        pred_value, change_pct, _ = prediction
        msk_time = datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')

        if self.btc == 0:
            if change_pct >= self.entry_threshold:
                self.buy(actual_price, msk_time)
        else:
            current_change = (actual_price - self.buy_price) / self.buy_price
            if current_change >= self.exit_threshold or change_pct < 0:
                self.sell(actual_price, msk_time)

    def buy(self, price: float, timestamp: str):
        if self.balance <= 0:
            return
        fee = self.balance * self.fee_pct
        amount = (self.balance - fee) / price
        self.btc = amount
        self.buy_price = price
        self.balance = 0

        log_entry = {
            'timestamp': timestamp,
            'type': 'BUY',
            'price': price,
            'amount': amount,
            'fee': fee,
            'balance': self.balance
        }
        self.trade_log.append(log_entry)
        self.balance_series.append((timestamp, self.balance))
        logger.info(f"Покупка: {amount:.6f} BTC по {price:.2f}, комиссия: {fee:.2f}")
        self.save_session()

    def sell(self, price: float, timestamp: str):
        if self.btc <= 0:
            return

        proceeds = self.btc * price
        fee = proceeds * self.fee_pct
        self.balance = proceeds - fee
        profit = self.balance - (self.btc * self.buy_price)

        log_entry = {
            'timestamp': timestamp,
            'type': 'SELL',
            'price': price,
            'amount': self.btc,
            'fee': fee,
            'balance': self.balance,
            'profit': profit
        }
        self.trade_log.append(log_entry)
        self.balance_series.append((timestamp, self.balance))
        logger.info(f"Продажа: {self.btc:.6f} BTC по {price:.2f}, комиссия: {fee:.2f}, прибыль: {profit:.2f}")
        self.save_session()

        self.btc = 0
        self.buy_price = 0

    def get_trade_log(self) -> List[Dict]:
        return self.trade_log

    def get_balance_series(self) -> List[Tuple[str, float]]:
        return self.balance_series

    def get_total_profit(self) -> float:
        return sum(log.get('profit', 0) for log in self.trade_log)

    def get_current_btc(self) -> float:
        return self.btc

    def get_current_balance(self) -> float:
        return self.balance

    def save_session(self):
        if not self.trade_log:
            return
        # Создаём папку simulations, если её нет
        os.makedirs("simulations", exist_ok=True)
        filename = f"simulations/simulation_{self.start_time}_{self.interval}.csv"
        save_to_csv(self.trade_log, self.metadata, filename)
