from datetime import datetime
from typing import List, Dict, Tuple
from utils.logger import setup_logger
from utils.csv_writer import save_to_csv, update_csv_accuracy
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import os
import time
import yaml

config = yaml.safe_load(open('config.yaml', 'r'))
log_frequency = config.get('log_frequency', 5)  # секунды

logger = setup_logger('simulator')

class TradeSimulator:
    def __init__(self, start_balance: float, entry_threshold: float, exit_threshold: float, fee_pct: float, interval: str, session_id: str):
        self.balance = start_balance
        self.btc = 0.0
        self.buy_price = 0.0
        self.fee_pct = fee_pct
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.interval = interval
        self.session_id = session_id

        self.trade_log = []
        self.balance_series = [
            (datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S'), start_balance)
        ]
        self.start_time = datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d_%H-%M-%S').replace(':', '-')

        self.metadata = {
            'session_id': self.session_id,
            'start_balance': self.balance,
            'entry_threshold': self.entry_threshold,
            'exit_threshold': self.exit_threshold,
            'fee_pct': self.fee_pct,
            'interval': self.interval,
            'start_time': self.start_time
        }

        self.correct_predictions = 0
        self.total_predictions = 0
        self.last_tick = None
        self.pending_log = None
        self.last_log_time = {'process_tick': 0, 'check_accuracy': 0, 'buy': 0, 'sell': 0}  # Rate limit для логов

        logger.info(
            f"Инициализация симулятора ({self.interval}, сессия {self.session_id}): "
            f"баланс={self.balance}, вход={self.entry_threshold}%, "
            f"выход={self.exit_threshold}%, комиссия={self.fee_pct}%"
        )

    def _can_log(self, log_type):
        if time.time() - self.last_log_time.get(log_type, 0) > log_frequency:
            self.last_log_time[log_type] = time.time()
            return True
        return False

    def check_prediction_accuracy(self, last_tick: Dict, current_price: float, operation: str) -> bool:
        last_actual_price = last_tick['actual_price']
        last_pred_change = last_tick['predictions'].get(self.interval)[1]
        actual_change = ((current_price - last_actual_price) / last_actual_price) * 100

        predicted_sign = 1 if last_pred_change > 0 else (-1 if last_pred_change < 0 else 0)
        actual_sign = 1 if actual_change > 0 else (-1 if actual_change < 0 else 0)
        is_correct = predicted_sign == actual_sign and predicted_sign != 0

        if self._can_log('check_accuracy'):
            logger.debug(f"Проверка точности ({operation}): предсказано {last_pred_change:.2f}%, реальное {actual_change:.2f}%, верно: {is_correct}")

        if predicted_sign != 0:
            self.total_predictions += 1
            if is_correct:
                self.correct_predictions += 1

        return is_correct

    def process_tick(self, tick: Dict):
        timestamp = tick['timestamp']
        price = tick['actual_price']
        predicted_price, predicted_change_pct, _ = tick['predictions'].get(self.interval, (None, None, None))

        if not predicted_price or not predicted_change_pct:
            if self._can_log('process_tick'):
                logger.warning(f"Отсутствуют предсказания для интервала {self.interval}, пропуск обработки")
            return

        if self.btc == 0 and predicted_change_pct >= self.entry_threshold:
            self.buy(timestamp, price, predicted_price, predicted_change_pct)
        elif self.btc > 0 and predicted_change_pct <= -self.exit_threshold:
            self.sell(timestamp, price, predicted_price, predicted_change_pct)

        self.last_tick = tick

    def buy(self, timestamp: str, price: float, predicted_price: float, predicted_change_pct: float):
        amount = self.balance / price
        fee = self.balance * self.fee_pct
        self.balance -= fee
        self.btc = amount
        self.buy_price = price

        buy_accuracy = None
        if self.last_tick:
            buy_accuracy = self.check_prediction_accuracy(self.last_tick, price, "BUY")

        self.pending_log = {
            'timestamp': timestamp,
            'type': 'BUY',
            'price': price,
            'amount': amount,
            'fee': fee,
            'balance': self.balance,
            'profit': None,
            'actual_price': price,
            'predicted_price': predicted_price,
            'predicted_change_pct': predicted_change_pct,
            'reason': f"Вход: Прогнозируемое изменение >= порога",
            'prediction_accuracy': buy_accuracy
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        if self._can_log('buy'):
            logger.info(f"Покупка (сессия {self.session_id}): {amount:.6f} BTC по {price:.2f}, комиссия: {fee:.2f} (fee_pct={self.fee_pct}%), причина: {self.pending_log['reason']}, точность: {buy_accuracy}")
        self.save_session()

    def sell(self, timestamp: str, price: float, predicted_price: float, predicted_change_pct: float):
        revenue = self.btc * price
        fee = revenue * self.fee_pct
        self.balance += revenue - fee
        profit = revenue - (self.btc * self.buy_price) - fee

        if self.pending_log:
            for i, log in enumerate(self.trade_log):
                if log['timestamp'] == self.pending_log['timestamp'] and log['type'] == 'BUY':
                    self.trade_log[i]['profit'] = profit
                    break
            self.update_session()

        sell_accuracy = None
        if self.last_tick:
            sell_accuracy = self.check_prediction_accuracy(self.last_tick, price, "SELL")

        self.pending_log = {
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
            'reason': f"Выход: Прогнозируемое отрицательное изменение",
            'prediction_accuracy': sell_accuracy
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        if self._can_log('sell'):
            logger.info(f"Продажа (сессия {self.session_id}): {self.btc:.6f} BTC по {price:.2f}, комиссия: {fee:.2f} (fee_pct={self.fee_pct}%), прибыль: {profit:.2f}, причина: {self.pending_log['reason']}, точность: {sell_accuracy}")
        self.save_session()

        self.btc = 0
        self.buy_price = 0
        self.pending_log = None

    def update_session(self):
        if not self.trade_log:
            return
        os.makedirs("simulations", exist_ok=True)
        filename = f"simulations/simulation_{self.session_id}.csv"
        logger.debug(f"Обновление сессии ({self.session_id}): вызов update_csv_accuracy с файлом {filename}")
        update_csv_accuracy(self.trade_log, self.metadata, filename, self.pending_log)

    def save_session(self):
        if not self.trade_log:
            return
        os.makedirs("simulations", exist_ok=True)
        filename = f"simulations/simulation_{self.session_id}.csv"
        logger.debug(f"Сохранение сессии ({self.session_id}): вызов save_to_csv с файлом {filename}")
        save_to_csv(self.trade_log, self.metadata, filename)

    def get_trade_log(self) -> List[Dict]:
        return self.trade_log

    def get_balance_series(self) -> List[Tuple[str, float]]:
        return self.balance_series

    def get_total_profit(self) -> float:
        return sum(float(log.get('profit') or 0) for log in self.trade_log)

    def get_current_btc(self) -> float:
        return self.btc

    def get_current_balance(self) -> float:
        return self.balance

    def get_prediction_accuracy(self) -> float:
        return (self.correct_predictions / self.total_predictions * 100) if self.total_predictions > 0 else 0.0