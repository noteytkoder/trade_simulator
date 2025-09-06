from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from utils.logger import setup_logger
from utils.csv_writer import save_to_csv, update_csv_accuracy
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import os

logger = setup_logger('simulator')
logger.setLevel('DEBUG')

class TradeSimulator:
    def __init__(self, start_balance: float, entry_threshold: float, exit_threshold: float,
                 fee_pct: float, interval: str, session_id: str,
                 mae_stop_enabled: bool = False, mae_stop_threshold: float = 12.0,
                 stop_loss_pct: float = 0.01, max_hold_minutes: int = 1, max_hold_seconds: int = 5):
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
        self.cost_basis = 0.0
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
            'stop_loss_pct': self.stop_loss_pct,
            'max_hold_minutes': max_hold_minutes,
            'max_hold_seconds': max_hold_seconds
        }
        self.correct_predictions = 0
        self.total_predictions = 0
        self.last_tick = None
        self.pending_log = None
        self.entry_time = None
        self.max_hold_minutes = max_hold_minutes
        self.max_hold_seconds = max_hold_seconds

        logger.info(
            f"Инициализация симулятора ({self.interval}, сессия {self.session_id}): "
            f"баланс={self.balance:.4f}, вход={self.entry_threshold:.6f}%, "
            f"выход={self.exit_threshold:.6f}%, комиссия={self.fee_pct:.6f}%, "
            f"MAE стоп={self.mae_stop_enabled}, MAE порог={self.mae_stop_threshold}, "
            f"стоп-лосс={self.stop_loss_pct * 100:.4f}%, макс. удержание={self.max_hold_minutes} мин / {self.max_hold_seconds} сек"
        )

    def calculate_fee(self, amount: float) -> float:
        return amount * (self.fee_pct / 100)

    def check_prediction_accuracy(self, last_tick: Dict, trade_price: float, operation: str) -> bool:
        last_actual_price = last_tick['actual_price']
        last_pred_change = last_tick['predictions'].get(self.interval)[1]
        actual_change = ((trade_price - last_actual_price) / last_actual_price) * 100
        predicted_sign = 1 if last_pred_change > 0 else -1 if last_pred_change < 0 else 0
        actual_sign = 1 if actual_change > 0 else -1 if actual_change < 0 else 0
        if predicted_sign == 0:
            logger.debug(f"[{self.session_id}] Нейтральный прогноз, точность не проверяется")
            return None
        is_correct = predicted_sign == actual_sign
        logger.debug(f"[{self.session_id}] Проверка точности: op={operation}, pred_change={last_pred_change:.6f}%, actual_change={actual_change:.6f}%, correct={is_correct}")
        return is_correct

    def set_stop_loss(self):
        if self.btc > 0:
            self.stop_loss_price = self.buy_price * (1 - self.stop_loss_pct)
            logger.debug(f"[{self.session_id}] Установлен стоп-лосс: {self.stop_loss_price:.4f}")

    def monitor_stop_loss(self, tick: Dict):
        trade_price = tick.get('realtime_price', tick['actual_price'])
        if self.btc > 0 and self.stop_loss_price is not None:
            new_sl = trade_price * (1 - self.stop_loss_pct)
            self.stop_loss_price = max(self.stop_loss_price, new_sl)
            logger.debug(f"[{self.session_id}] Мониторинг стоп-лосс: price={trade_price:.4f}, sl_price={self.stop_loss_price:.4f}")
            if trade_price <= self.stop_loss_price:
                logger.warning(f"[{self.session_id}] Сработал стоп-лосс: price={trade_price:.4f} <= {self.stop_loss_price:.4f}")
                self.sell(tick['timestamp'], trade_price, None, None, reason="Стоп-лосс")
                self.auto_paused = False

    def process_tick(self, tick: Dict):
        timestamp = tick['timestamp']
        trade_price = tick.get('realtime_price', tick['actual_price'])
        prediction = tick['predictions'].get(self.interval)
        self.last_mae = tick.get('mae_10min')
        if self.last_mae is not None:
            self.mae_series.append((timestamp, self.last_mae))

        logger.info(f"[{self.session_id}] Тик: time={timestamp}, trade_price={trade_price:.4f}, pred={prediction}, mae={self.last_mae}, in_position={self.btc > 0}, paused={self.auto_paused}")

        self.monitor_stop_loss(tick)

        if self.auto_paused:
            logger.info(f"[{self.session_id}] Авто-пауза активна, пропуск сигналов")
            return

        if self.mae_stop_enabled and self.last_mae is not None and self.last_mae > self.mae_stop_threshold:
            logger.warning(f"[{self.session_id}] MAE {self.last_mae:.4f} > {self.mae_stop_threshold}, авто-пауза и стоп-лосс")
            self.auto_paused = True
            self.set_stop_loss()
            return

        if not prediction:
            logger.info(f"[{self.session_id}] Нет предсказания для текущего тика")
            return

        predicted_price, predicted_change_pct, forecast_time = prediction
        logger.debug(f"[{self.session_id}] Предсказание: price={predicted_price:.4f}, change={predicted_change_pct:.6f}%, time={forecast_time}")

        if self.btc == 0:
            if predicted_change_pct >= self.entry_threshold:
                logger.info(f"[{self.session_id}] Сигнал BUY: change={predicted_change_pct:.6f}% >= {self.entry_threshold:.6f}%")
                self.buy(timestamp, trade_price, predicted_price, predicted_change_pct)
            else:
                logger.debug(f"[{self.session_id}] Нет BUY: change={predicted_change_pct:.6f}% < {self.entry_threshold:.6f}%")
        else:
            current_profit = (trade_price - self.buy_price) / self.buy_price * 100
            sell_reason = None

            if current_profit >= self.exit_threshold:
                sell_reason = "Выход: прибыль >= порога"
            elif predicted_change_pct < 0:
                sell_reason = "Выход: прогноз стал отрицательным"
            elif current_profit <= -self.stop_loss_pct:
                sell_reason = "Выход: стоп-лосс"
            elif self.entry_time:
                now = datetime.now(ZoneInfo("Europe/Moscow"))
                hold_time = now - self.entry_time
                if self.interval == '5s' and hold_time.total_seconds() > self.max_hold_seconds and current_profit < 0:
                    sell_reason = f"Выход: удержание > {self.max_hold_seconds} сек и убыток"
                elif self.interval == '1m' and hold_time > timedelta(minutes=self.max_hold_minutes) and current_profit < 0:
                    sell_reason = f"Выход: удержание > {self.max_hold_minutes} мин и убыток"
            elif self.last_mae is not None and self.last_mae > self.mae_stop_threshold and current_profit < 0:
                sell_reason = f"Выход: высокая MAE {self.last_mae:.4f} и убыток"

            logger.info(f"[{self.session_id}] Решение: current_profit={current_profit:.6f}%, pred_change={predicted_change_pct:.6f}%, decision={sell_reason or 'hold'}")

            if sell_reason:
                self.sell(timestamp, trade_price, predicted_price, predicted_change_pct, reason=sell_reason)

        self.last_tick = tick

    def buy(self, timestamp: str, trade_price: float, predicted_price: float, predicted_change_pct: float):
        if self.balance <= 0:
            logger.warning(f"[{self.session_id}] BUY отменён: недостаточно средств")
            return

        fee = self.calculate_fee(self.balance)
        net_balance = self.balance - fee
        self.btc = net_balance / trade_price
        self.buy_price = trade_price
        self.cost_basis = self.balance
        self.balance = 0.0
        self.set_stop_loss()
        self.entry_time = datetime.now(ZoneInfo("Europe/Moscow"))

        buy_accuracy = None
        if self.last_tick:
            buy_accuracy = self.check_prediction_accuracy(self.last_tick, trade_price, "BUY")
            if buy_accuracy is not None:
                self.total_predictions += 1
                if buy_accuracy:
                    self.correct_predictions += 1

        self.pending_log = {
            'timestamp': timestamp,
            'type': 'BUY',
            'price': trade_price,
            'amount': self.btc,
            'fee': fee,
            'balance': self.balance,
            'actual_price': self.last_tick['actual_price'] if self.last_tick else trade_price,
            'trade_price': trade_price,
            'predicted_price': predicted_price,
            'predicted_change_pct': predicted_change_pct,
            'reason': 'Вход: прогноз >= порога',
            'prediction_accuracy': buy_accuracy,
            'mae_10min': self.last_mae,
            'accuracy_pct': self.get_prediction_accuracy()
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        logger.info(f"BUY ({self.session_id}): {self.btc:.6f} BTC по {trade_price:.4f}, комиссия={fee:.4f}")
        self.save_session()

    def sell(self, timestamp: str, trade_price: float, predicted_price: float, predicted_change_pct: float, reason: str = None):
        if self.btc <= 0:
            logger.warning(f"[{self.session_id}] SELL отменён: нет BTC")
            return

        proceeds = self.btc * trade_price
        fee = self.calculate_fee(proceeds)
        net_proceeds = proceeds - fee
        profit = net_proceeds - self.cost_basis
        self.balance = net_proceeds

        if reason is None:
            reason = "Стоп-лосс" if predicted_price is None else "Выход: прибыль/прогноз"

        self.pending_log = {
            'timestamp': timestamp,
            'type': 'SELL',
            'price': trade_price,
            'amount': self.btc,
            'fee': fee,
            'balance': self.balance,
            'profit': profit,
            'actual_price': self.last_tick['actual_price'] if self.last_tick else trade_price,
            'trade_price': trade_price,
            'predicted_price': predicted_price,
            'predicted_change_pct': predicted_change_pct,
            'reason': reason,
            'prediction_accuracy': None,
            'mae_10min': self.last_mae,
            'accuracy_pct': self.get_prediction_accuracy()
        }
        self.trade_log.append(self.pending_log)
        self.balance_series.append((timestamp, self.balance))
        self.profit_series.append((timestamp, profit))
        self.accuracy_series.append((timestamp, self.get_prediction_accuracy()))
        if profit < 0:
            logger.warning(f"SELL ({self.session_id}): {self.btc:.6f} BTC по {trade_price:.4f}, комиссия={fee:.6f}, убыток={profit:.6f}, reason={reason}")
        else:
            logger.info(f"SELL ({self.session_id}): {self.btc:.6f} BTC по {trade_price:.4f}, комиссия={fee:.6f}, прибыль={profit:.6f}, reason={reason}")
        self.save_session()

        self.btc = 0.0
        self.buy_price = 0.0
        self.cost_basis = 0.0
        self.pending_log = None
        self.stop_loss_price = None
        self.entry_time = None

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
