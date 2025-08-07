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
        self.correct_predictions = 0
        self.total_predictions = 0
        self.last_predicted_change = None
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
                self.last_predicted_change = change_pct
                self.buy(actual_price, msk_time, pred_value, change_pct, "Entry: Predicted change >= threshold")
        else:
            current_change = (actual_price - self.buy_price) / self.buy_price
            reason = None
            if current_change >= self.exit_threshold:
                reason = "Exit: Profit >= threshold"
            elif change_pct < 0:
                reason = "Exit: Predicted negative change"
            if reason:
                # Проверяем точность прогноза
                actual_change = (actual_price - self.buy_price) / self.buy_price
                is_correct = (self.last_predicted_change > 0 and actual_change > 0) or \
                            (self.last_predicted_change < 0 and actual_change < 0)
                self.total_predictions += 1
                if is_correct:
                    self.correct_predictions += 1
                self.sell(actual_price, msk_time, pred_value, change_pct, reason, is_correct)
                self.last_predicted_change = None

    def buy(self, price: float, timestamp: str, predicted_price: float, predicted_change_pct: float, reason: str):
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
            'balance': self.balance,
            'actual_price': price,
            'predicted_price': predicted_price,
            'predicted_change_pct': predicted_change_pct,
            'reason': reason
        }
        self.trade_log.append(log_entry)
        self.balance_series.append((timestamp, self.balance))
        logger.info(f"Покупка: {amount:.6f} BTC по {price:.2f}, комиссия: {fee:.2f}, причина: {reason}")
        self.save_session()

    def sell(self, price: float, timestamp: str, predicted_price: float, predicted_change_pct: float, reason: str, prediction_accuracy: bool):
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
            'profit': profit,
            'actual_price': price,
            'predicted_price': predicted_price,
            'predicted_change_pct': predicted_change_pct,
            'reason': reason,
            'prediction_accuracy': prediction_accuracy
        }
        self.trade_log.append(log_entry)
        self.balance_series.append((timestamp, self.balance))
        logger.info(f"Продажа: {self.btc:.6f} BTC по {price:.2f}, комиссия: {fee:.2f}, прибыль: {profit:.2f}, причина: {reason}, точность: {prediction_accuracy}")
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

    def get_prediction_accuracy(self) -> float:
        return (self.correct_predictions / self.total_predictions * 100) if self.total_predictions > 0 else 0.0

    def save_session(self):
        if not self.trade_log:
            return
        os.makedirs("simulations", exist_ok=True)
        filename = f"simulations/simulation_{self.start_time}_{self.interval}.csv"
        save_to_csv(self.trade_log, self.metadata, filename)