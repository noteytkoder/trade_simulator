from datetime import datetime
from typing import List, Dict, Tuple
from utils.logger import setup_logger
from utils.csv_writer import save_to_csv, update_csv_accuracy
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import os
import yaml

logger = setup_logger('simulator')

class TradeSimulator:
    def __init__(self, start_balance: float, entry_threshold: float, exit_threshold: float, fee_pct: float, interval: str, session_id: str,
                 mae_stop_enabled: bool = True, mae_stop_threshold: float = 12.0, stop_loss_pct: float = 0.01):
        self.balance = start_balance
        self.btc = 0.0
        self.buy_price = 0.0
        self.fee_pct = fee_pct
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.interval = interval
        self.session_id = session_id

        self.mae_stop_enabled = mae_stop_enabled
        self.mae_stop_threshold = mae_stop_threshold
        self.stop_loss_pct = stop_loss_pct
        self.stop_loss_price = None
        self.auto_paused = False
        self.last_mae = None

        self.trade_log = []
        self.balance_series = [
            (datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S'), start_balance)
        ]
        self.profit_series = []
        self.accuracy_series = []
        self.mae_series = []
        self.start_time = datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d_%H-%M-%S').replace(':', '-')

        self.metadata = {
            'session_id': self.session_id,
            'start_balance': self.balance,
            'entry_threshold': self.entry_threshold,
            'exit_threshold': self.exit_threshold,
            'fee_pct': self.fee_pct,
            'interval': self.interval,
            'start_time': self.start_time,
            'mae_stop_enabled': self.mae_stop_enabled,
            'mae_stop_threshold': self.mae_stop_threshold,
            'stop_loss_pct': self.stop_loss_pct
        }

        self.correct_predictions = 0
        self.total_predictions = 0
        self.last_tick = None
        self.pending_log = None

        logger.info(
            f"Инициализация симулятора ({self.interval}, сессия {self.session_id}): "
            f"баланс={self.balance:.2f}, вход={self.entry_threshold:.6f}%, "
            f"выход={self.exit_threshold:.6f}%, комиссия={self.fee_pct:.6f}%, "
            f"MAE стоп={self.mae_stop_enabled}, MAE порог={self.mae_stop_threshold}, "
            f"стоп-лосс %={self.stop_loss_pct}"
        )

    def check_prediction_accuracy(self, last_tick: Dict, current_price: float, operation: str) -> bool:
        last_actual_price = last_tick['actual_price']
        last_pred_change = last_tick['predictions'].get(self.interval)[1]
        actual_change = ((current_price - last_actual_price) / last_actual_price) * 100

        predicted_sign = 1 if last_pred_change > 0 else (-1 if last_pred_change < 0 else 0)
        actual_sign = 1 if actual_change > 0 else (-1 if actual_change < 0 else 0)
        is_correct = predicted_sign == actual_sign and predicted_sign != 0

        if predicted_sign != 0:
            self.total_predictions += 1
            if is_correct:
                self.correct_predictions += 1

        logger.info(
            f"Проверка точности ({operation}, сессия {self.session_id}): "
            f"предсказано {last_pred_change:.6f}%, реальное {actual_change:.6f}%, "
            f"верно: {is_correct}, correct/total={self.correct_predictions}/{self.total_predictions}"
        )
        return is_correct

    def process_tick(self, tick: Dict):
        timestamp = tick['timestamp']
        price = tick['actual_price']
        prediction = tick['predictions'].get(self.interval)
        self.last_mae = tick.get('mae_10min')
        if self.last_mae is not None:
            self.mae_series.append((timestamp, self.last_mae))

        self.monitor_stop_loss(tick)

        if self.auto_paused:
            logger.info(f"[{self.interval}, сессия {self.session_id}] Авто-пауза активна, пропуск сигналов")
            return

        if self.mae_stop_enabled and self.last_mae is not None and self.last_mae > self.mae_stop_threshold:
            logger.warning(f"[{self.interval}, сессия {self.session_id}] MAE {self.last_mae:.4f} > {self.mae_stop_threshold}, авто-пауза и установка стоп-лосса")
            self.auto_paused = True
            self.set_stop_loss()
            return

        if not prediction:
            logger.info(f"[{self.interval}, сессия {self.session_id}] Нет предсказания для текущего тика.")
            return

        predicted_price, predicted_change_pct, _ = prediction

        if self.btc == 0:
            logger.info(
                f"[{self.interval}, сессия {self.session_id}] Проверка на покупку: "
                f"change_pct >= entry_threshold? {predicted_change_pct:.6f} >= {self.entry_threshold:.6f}"
            )
            if predicted_change_pct >= self.entry_threshold:
                logger.info(
                    f"[{self.interval}, сессия {self.session_id}] Сигнал на покупку с "
                    f"change_pct={predicted_change_pct:.6f}% (порог {self.entry_threshold:.6f}%)"
                )
                self.buy(timestamp, price, predicted_price, predicted_change_pct)
                return
        elif self.btc > 0:
            logger.info(
                f"[{self.interval}, сессия {self.session_id}] Проверка на продажу: "
                f"change_pct <= -exit_threshold? {predicted_change_pct:.6f} <= {-self.exit_threshold:.6f}"
            )
            if predicted_change_pct <= -self.exit_threshold:
                logger.info(
                    f"[{self.interval}, сессия {self.session_id}] Сигнал на продажу с "
                    f"change_pct={predicted_change_pct:.6f}% (порог {-self.exit_threshold:.6f}%)"
                )
                self.sell(timestamp, price, predicted_price, predicted_change_pct)
                return

        self.last_tick = tick

    def monitor_stop_loss(self, tick: Dict):
        if self.stop_loss_price is not None and self.btc > 0:
            price = tick['actual_price']
            timestamp = tick['timestamp']
            if price <= self.stop_loss_price:
                logger.info(f"[{self.interval}, сессия {self.session_id}] Стоп-лосс сработал по цене {price:.2f}")
                self.sell(timestamp, price, None, None)
                if self.pending_log:
                    self.pending_log['reason'] = "Стоп-лосс сработал"
                self.stop_loss_price = None

    def set_stop_loss(self):
        if self.btc > 0:
            self.stop_loss_price = self.buy_price * (1 - self.stop_loss_pct)
            logger.info(f"[{self.interval}, сессия {self.session_id}] Установлен стоп-лосс на {self.stop_loss_price:.2f}")

    def buy(self, timestamp: str, price: float, predicted_price: float, predicted_change_pct: float):
        amount = self.balance / price
        fee = self.balance * self.fee_pct
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
            'reason': "Вход: Прогнозируемое изменение >= порога",
            'prediction_accuracy': buy_accuracy,
            'mae_10min': self.last_mae,
            'accuracy_pct': self.get_prediction_accuracy()
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        self.accuracy_series.append((timestamp, self.get_prediction_accuracy()))
        logger.info(
            f"Покупка (сессия {self.session_id}): {amount:.6f} BTC по {price:.2f}, "
            f"комиссия: {fee:.2f}, баланс: {self.balance:.2f}, причина: {self.pending_log['reason']}, "
            f"точность: {buy_accuracy}, MAE 10min: {self.last_mae}, accuracy_pct: {self.get_prediction_accuracy():.2f}%"
        )
        self.save_session()

    def sell(self, timestamp: str, price: float, predicted_price: float, predicted_change_pct: float):
        if self.btc <= 0:
            logger.warning(f"[{self.interval}, сессия {self.session_id}] Отмена продажи: нет BTC для продажи (btc={self.btc})")
            return

        proceeds = self.btc * price
        fee = proceeds * self.fee_pct
        profit = proceeds - (self.btc * self.buy_price) - fee
        self.balance = proceeds - fee

        buy_accuracy = None
        if self.pending_log and self.last_tick and self.pending_log['type'] == 'BUY':
            buy_accuracy = self.check_prediction_accuracy(self.last_tick, price, "BUY")
            for i, log in enumerate(self.trade_log):
                if log['timestamp'] == self.pending_log['timestamp'] and log['type'] == 'BUY':
                    self.trade_log[i]['prediction_accuracy'] = buy_accuracy
                    self.trade_log[i]['profit'] = profit
                    break
            self.update_session()

        sell_accuracy = None
        if self.last_tick and predicted_price is not None:
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
            'reason': "Выход: Прогнозируемое отрицательное изменение" if predicted_price else "Стоп-лосс",
            'prediction_accuracy': sell_accuracy,
            'mae_10min': self.last_mae,
            'accuracy_pct': self.get_prediction_accuracy()
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        self.profit_series.append((timestamp, profit))
        self.accuracy_series.append((timestamp, self.get_prediction_accuracy()))
        logger.info(
            f"Продажа (сессия {self.session_id}): {self.btc:.6f} BTC по {price:.2f}, "
            f"комиссия: {fee:.2f}, баланс: {self.balance:.2f}, прибыль: {profit:.2f}, "
            f"причина: {self.pending_log['reason']}, точность: {sell_accuracy}, "
            f"MAE 10min: {self.last_mae}, accuracy_pct: {self.get_prediction_accuracy():.2f}%"
        )
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

    def get_profit_series(self) -> List[Tuple[str, float]]:
        return self.profit_series

    def get_accuracy_series(self) -> List[Tuple[str, float]]:
        return self.accuracy_series

    def get_mae_series(self) -> List[Tuple[str, float]]:
        return self.mae_series

    def get_total_profit(self) -> float:
        return sum(float(log.get('profit') or 0) for log in self.trade_log)

    def get_current_btc(self) -> float:
        return self.btc

    def get_current_balance(self) -> float:
        return self.balance

    def get_prediction_accuracy(self) -> float:
        return (self.correct_predictions / self.total_predictions * 100) if self.total_predictions > 0 else 0.0

    def get_last_mae(self) -> float:
        return self.last_mae