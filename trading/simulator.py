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
    def __init__(self, start_balance: float, entry_threshold: float, exit_threshold: float,
                 fee_pct: float, interval: str, session_id: str,
                 mae_stop_enabled: bool = True, mae_stop_threshold: float = 12.0,
                 stop_loss_pct: float = 0.01):
        self.balance = start_balance
        self.btc = 0.0
        self.buy_price = 0.0
        self.fee_pct = fee_pct  # В процентах: 0.075 = 0.075%
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.interval = interval
        self.session_id = session_id

        # MAE/стоп-лосс
        self.mae_stop_enabled = mae_stop_enabled
        self.mae_stop_threshold = mae_stop_threshold
        self.stop_loss_pct = stop_loss_pct
        self.stop_loss_price = None
        self.auto_paused = False
        self.last_mae = None

        # Затраты на вход (для корректного профита)
        self.cost_basis = 0.0

        # Логи и метрики
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
            f"стоп-лосс={self.stop_loss_pct * 100:.2f}%"
        )

    # ------------------ Единый расчёт комиссии ------------------

    def calculate_fee(self, amount: float) -> float:
        """Возвращает комиссию в USDT (или эквиваленте) исходя из процента"""
        return amount * (self.fee_pct / 100)

    # ------------------ Проверка точности ------------------

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

    # ------------------ Основной цикл ------------------

    def process_tick(self, tick: Dict):
        timestamp = tick['timestamp']
        price = tick['actual_price']
        prediction = tick['predictions'].get(self.interval)
        self.last_mae = tick.get('mae_10min')
        if self.last_mae is not None:
            self.mae_series.append((timestamp, self.last_mae))

        self.monitor_stop_loss(tick)

        if self.auto_paused:
            logger.info(f"[{self.interval}, {self.session_id}] Авто-пауза активна, пропуск сигналов")
            return

        if self.mae_stop_enabled and self.last_mae is not None and self.last_mae > self.mae_stop_threshold:
            logger.warning(f"[{self.interval}, {self.session_id}] MAE {self.last_mae:.4f} > {self.mae_stop_threshold}, авто-пауза и стоп-лосс")
            self.auto_paused = True
            self.set_stop_loss()
            return

        if not prediction:
            logger.info(f"[{self.interval}, {self.session_id}] Нет предсказания для текущего тика.")
            return

        predicted_price, predicted_change_pct, _ = prediction

        if self.btc == 0:
            if predicted_change_pct >= self.entry_threshold:
                self.buy(timestamp, price, predicted_price, predicted_change_pct)
                return
        else:
            current_change = ((price - self.buy_price) / self.buy_price) * 100
            if current_change >= self.exit_threshold or predicted_change_pct <= -self.exit_threshold:
                self.sell(timestamp, price, predicted_price, predicted_change_pct)
                return

        self.last_tick = tick

    # ------------------ Стоп-лосс ------------------

    def monitor_stop_loss(self, tick: Dict):
        if self.stop_loss_price is not None and self.btc > 0:
            price = tick['actual_price']
            timestamp = tick['timestamp']
            if price <= self.stop_loss_price:
                logger.info(f"[{self.interval}, {self.session_id}] Стоп-лосс сработал по цене {price:.2f}")
                self.sell(timestamp, price, None, None)
                if self.pending_log:
                    self.pending_log['reason'] = "Стоп-лосс"
                self.stop_loss_price = None

    def set_stop_loss(self):
        if self.btc > 0:
            self.stop_loss_price = self.buy_price * (1 - self.stop_loss_pct)
            logger.info(f"[{self.interval}, {self.session_id}] Установлен стоп-лосс на {self.stop_loss_price:.2f}")

    # ------------------ BUY ------------------

    def buy(self, timestamp: str, price: float, predicted_price: float, predicted_change_pct: float):
        cost = self.balance
        fee = self.calculate_fee(cost)
        net_cost = cost - fee
        amount = net_cost / price

        self.btc = amount
        self.buy_price = price
        self.balance = 0.0
        self.cost_basis = net_cost

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
            'reason': "Вход: прогноз >= порога",
            'prediction_accuracy': buy_accuracy,
            'mae_10min': self.last_mae,
            'accuracy_pct': self.get_prediction_accuracy()
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        self.accuracy_series.append((timestamp, self.get_prediction_accuracy()))
        logger.info(f"BUY ({self.session_id}): {amount:.6f} BTC по {price:.2f}, комиссия={fee:.2f}")
        self.save_session()

    # ------------------ SELL ------------------

    def sell(self, timestamp: str, price: float, predicted_price: float, predicted_change_pct: float):
        if self.btc <= 0:
            logger.warning(f"[{self.interval}, {self.session_id}] SELL отменён: нет BTC")
            return

        proceeds = self.btc * price
        fee = self.calculate_fee(proceeds)
        net_proceeds = proceeds - fee

        profit = net_proceeds - self.cost_basis
        self.balance = net_proceeds

        sell_accuracy = None
        if self.last_tick and predicted_price is not None:
            sell_accuracy = self.check_prediction_accuracy(self.last_tick, price, "SELL")

        reason = "Выход: прибыль/прогноз" if predicted_price else "Стоп-лосс"
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
            'prediction_accuracy': sell_accuracy,
            'mae_10min': self.last_mae,
            'accuracy_pct': self.get_prediction_accuracy()
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        self.profit_series.append((timestamp, profit))
        self.accuracy_series.append((timestamp, self.get_prediction_accuracy()))
        logger.info(f"SELL ({self.session_id}): {self.btc:.6f} BTC по {price:.2f}, комиссия={fee:.2f}, прибыль={profit:.2f}")
        self.save_session()

        self.btc = 0.0
        self.buy_price = 0.0
        self.cost_basis = 0.0
        self.pending_log = None
        self.stop_loss_price = None

    # ------------------ Сессия/CSV ------------------

    def update_session(self):
        if not self.trade_log:
            return
        os.makedirs("simulations", exist_ok=True)
        filename = f"simulations/simulation_{self.session_id}.csv"
        update_csv_accuracy(self.trade_log, self.metadata, filename, self.pending_log)

    def save_session(self):
        if not self.trade_log:
            return
        os.makedirs("simulations", exist_ok=True)
        filename = f"simulations/simulation_{self.session_id}.csv"
        save_to_csv(self.trade_log, self.metadata, filename)

    # ------------------ Методы доступа ------------------

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
