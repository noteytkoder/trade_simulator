from datetime import datetime
from typing import List, Dict, Tuple
from utils.logger import setup_logger
from utils.csv_writer import save_to_csv, update_csv_accuracy
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import os

logger = setup_logger('simulator')

class TradeSimulator:
    def __init__(self, start_balance: float, entry_threshold: float, exit_threshold: float, fee_pct: float, interval: str):
        self.balance = start_balance
        self.btc = 0.0
        self.buy_price = 0.0
        self.fee_pct = fee_pct
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.interval = interval
        self.trade_log = []
        self.balance_series = [(datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S'), start_balance)]
        self.start_time = datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d_%H-%M-%S').replace(':', '-')
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
        self.last_tick = None  # Храним предыдущий тик
        self.pending_log = None  # Временное хранение лога для BUY
        logger.info(f"Инициализация симулятора ({interval}): баланс={start_balance}, entry={entry_threshold}%, exit={exit_threshold}%, fee={fee_pct}%")

    def check_prediction_accuracy(self, last_tick: Dict, current_price: float, operation: str) -> bool:
        """Проверяет, совпадает ли знак прогноза и фактического изменения."""
        last_actual_price = last_tick['actual_price']
        last_pred_change = last_tick['predictions'].get(self.interval)[1]  # predicted_change_pct в процентах
        actual_change = ((current_price - last_actual_price) / last_actual_price) * 100  # В процентах

        predicted_sign = 1 if last_pred_change > 0 else (-1 if last_pred_change < 0 else 0)
        actual_sign = 1 if actual_change > 0 else (-1 if actual_change < 0 else 0)
        is_correct = (predicted_sign == actual_sign)

        self.total_predictions += 1
        if is_correct:
            self.correct_predictions += 1

        logger.info(
            f"Проверка точности ({operation}): predicted_change={last_pred_change:.6f}%, "
            f"actual_change={actual_change:.6f}%, predicted_sign={predicted_sign}, "
            f"actual_sign={actual_sign}, is_correct={is_correct}, "
            f"correct/total={self.correct_predictions}/{self.total_predictions}"
        )
        return is_correct

    def process_tick(self, tick: Dict):
        actual_price = tick['actual_price']
        prediction = tick['predictions'].get(self.interval)
        if not prediction:
            return

        pred_value, change_pct, _ = prediction
        msk_time = datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')

        # Если позиции нет — ищем сигнал на покупку
        if self.btc == 0:
            if change_pct >= self.entry_threshold:
                self.buy(actual_price, msk_time, pred_value, change_pct, "Вход: Прогнозируемое изменение >= порога")
                return  # Предотвращаем повторные покупки в одном тике

        # Если позиция открыта — проверяем условия выхода
        else:
            current_change = ((actual_price - self.buy_price) / self.buy_price) * 100
            reason = None
            if current_change >= self.exit_threshold:
                reason = "Выход: Прибыль >= порога"
            elif change_pct < 0:
                reason = "Выход: Прогнозируемое отрицательное изменение"

            if reason:
                self.sell(actual_price, msk_time, pred_value, change_pct, reason)
                return  # Предотвращаем повторные продажи в одном тике

        # Обновляем last_tick, если ничего не делали
        self.last_tick = tick

    def buy(self, price: float, timestamp: str, predicted_price: float, predicted_change_pct: float, reason: str):
        if self.balance <= 0:
            return
        fee = self.balance * self.fee_pct
        amount = (self.balance - fee) / price
        self.btc = amount
        self.buy_price = price
        self.balance = 0

        # Для BUY точность не проверяем (ждём закрытия позиции)
        self.pending_log = {
            'timestamp': timestamp,
            'type': 'BUY',
            'price': price,
            'amount': amount,
            'fee': fee,
            'balance': self.balance,
            'actual_price': price,
            'predicted_price': predicted_price,
            'predicted_change_pct': predicted_change_pct,
            'reason': reason,
            'prediction_accuracy': None  # Будет обновлено при SELL
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        logger.info(f"Покупка: {amount:.6f} BTC по {price:.2f}, комиссия: {fee:.2f}, причина: {reason}, точность: None")
        self.save_session()

    def sell(self, price: float, timestamp: str, predicted_price: float, predicted_change_pct: float, reason: str):
        if self.btc <= 0:
            return

        proceeds = self.btc * price
        fee = proceeds * self.fee_pct
        self.balance = proceeds - fee
        profit = self.balance - (self.btc * self.buy_price)

        # Проверяем точность для BUY, если позиция открыта
        buy_accuracy = None
        if self.pending_log and self.last_tick and self.pending_log['type'] == 'BUY':
            buy_accuracy = self.check_prediction_accuracy(self.last_tick, price, "BUY")
            for i, log in enumerate(self.trade_log):
                if log['timestamp'] == self.pending_log['timestamp'] and log['type'] == 'BUY':
                    self.trade_log[i]['prediction_accuracy'] = buy_accuracy
                    break
            self.update_session()

        # Проверяем точность для SELL
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
            'reason': reason,
            'prediction_accuracy': sell_accuracy
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        logger.info(f"Продажа: {self.btc:.6f} BTC по {price:.2f}, комиссия: {fee:.2f}, прибыль: {profit:.2f}, причина: {reason}, точность: {sell_accuracy}")
        self.save_session()

        self.btc = 0
        self.buy_price = 0
        self.pending_log = None  # Сбрасываем после SELL

    def update_session(self):
        if not self.trade_log:
            return
        os.makedirs("simulations", exist_ok=True)
        filename = f"simulations/simulation_{self.start_time}_{self.interval}.csv"
        logger.debug(f"Обновление сессии: вызов update_csv_accuracy с файлом {filename}")
        update_csv_accuracy(self.trade_log, self.metadata, filename, self.pending_log)

    def save_session(self):
        if not self.trade_log:
            return
        os.makedirs("simulations", exist_ok=True)
        filename = f"simulations/simulation_{self.start_time}_{self.interval}.csv"
        logger.debug(f"Сохранение сессии: вызов save_to_csv с файлом {filename}")
        save_to_csv(self.trade_log, self.metadata, filename)

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