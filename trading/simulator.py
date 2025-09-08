from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
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
    def __init__(self,
                 start_balance: float,
                 entry_threshold: float,
                 exit_threshold: float,
                 fee_pct: float,
                 interval: str,
                 session_id: str,
                 mae_stop_enabled: bool = False,
                 mae_stop_threshold: float = 12.0,
                 stop_loss_pct: float = 1.0,          # проценты (1.0 = 1%)
                 trailing_stop_pct: float = 0.0,       # проценты (0.5 = 0.5%)
                 max_hold_minutes: int = 1,
                 max_hold_seconds: int = 5,
                 cooldown_seconds: Optional[int] = None,
                 prediction_valid_seconds: Optional[int] = None):

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
        self.trailing_stop_pct = trailing_stop_pct
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
            'trailing_stop_pct': self.trailing_stop_pct,
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

        # max_hold на основе interval
        if self.interval == '5s':
            self.max_hold = timedelta(seconds=self.max_hold_seconds)
        elif self.interval == '1m':
            self.max_hold = timedelta(minutes=self.max_hold_minutes)
        elif self.interval == '1h':
            self.max_hold = timedelta(hours=1)  # Пример, можно настроить в конфиге
        else:
            raise ValueError(f"Неподдерживаемый интервал: {self.interval}")

        # prediction / realtime helpers
        self.last_prediction: Optional[Dict] = None
        self.peak_price: Optional[float] = None
        self.cooldown_until: Optional[datetime] = None

        # sensible defaults if не заданы
        default_cooldown = {'5s': 2, '1m': 30, '1h': 1800}  # 30 мин для часа, пример
        default_pred_valid = {'5s': 10, '1m': 120, '1h': 7200}  # 2 часа для часа, пример

        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else default_cooldown.get(interval, 30)
        self.prediction_valid_seconds = prediction_valid_seconds if prediction_valid_seconds is not None else default_pred_valid.get(interval, 120)

        logger.info(
            f"Инициализация симулятора ({self.interval}, сессия {self.session_id}): "
            f"баланс={self.balance:.4f}, вход={self.entry_threshold:.3f}%, "
            f"выход={self.exit_threshold:.3f}%, комиссия={self.fee_pct:.3f}%, "
            f"MAE стоп={self.mae_stop_enabled}, MAE порог={self.mae_stop_threshold}, "
            f"стоп-лосс={self.stop_loss_pct:.3f}%, trailing={self.trailing_stop_pct:.3f}%, "
            f"max_hold={self.max_hold}, "
            f"cooldown={self.cooldown_seconds}s, pred_valid={self.prediction_valid_seconds}s"
        )

    def calculate_fee(self, amount: float) -> float:
        return amount * (self.fee_pct / 100)

    def check_prediction_accuracy(self, last_tick: Dict, trade_price: float, operation: str) -> Optional[bool]:
        try:
            last_actual_price = float(last_tick['actual_price'])
            last_pred_change = last_tick['predictions'].get(self.interval)[1]
        except Exception:
            return None

        actual_change = ((trade_price - last_actual_price) / last_actual_price) * 100
        predicted_sign = 1 if last_pred_change > 0 else -1 if last_pred_change < 0 else 0
        actual_sign = 1 if actual_change > 0 else -1 if actual_change < 0 else 0
        if predicted_sign == 0:
            return None
        return predicted_sign == actual_sign

    def set_stop_loss(self):
        if self.btc > 0:
            self.stop_loss_price = self.buy_price * (1 - self.stop_loss_pct / 100)

    def monitor_stop_loss(self, tick: Dict):
        trade_price = float(tick.get('realtime_price', tick.get('actual_price')))
        if self.btc > 0:
            if self.peak_price is None or trade_price > self.peak_price:
                self.peak_price = trade_price

            if self.stop_loss_price is not None:
                new_sl = trade_price * (1 - self.stop_loss_pct / 100)
                self.stop_loss_price = max(self.stop_loss_price, new_sl)

            if self.trailing_stop_pct > 0 and self.peak_price is not None:
                trailing_level = self.peak_price * (1 - self.trailing_stop_pct / 100)
                if trade_price <= trailing_level:
                    self.sell(tick['timestamp'], trade_price, None, None, reason="Trailing-stop")
                    self.auto_paused = False
                    return

            if self.stop_loss_price is not None and trade_price <= self.stop_loss_price:
                self.sell(tick['timestamp'], trade_price, None, None, reason="Стоп-лосс")
                self.auto_paused = False

    def process_tick(self, tick: Dict):
        timestamp = tick['timestamp']
        trade_price = float(tick.get('realtime_price', tick.get('actual_price')))
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        self.last_mae = tick.get('mae_10min', 0)
        self.mae_series.append((timestamp, self.last_mae))

        if self.mae_stop_enabled and self.last_mae > self.mae_stop_threshold:
            self.auto_paused = True
        else:
            self.auto_paused = False

        if self.auto_paused:
            if self.btc > 0:
                self.sell(timestamp, trade_price, None, None, reason="Авто-пауза: высокая MAE")
            self.last_tick = tick
            return

        predicted_price, predicted_change_pct, forecast_time = tick['predictions'].get(self.interval, (0, 0, ''))

        if self.cooldown_until and now < self.cooldown_until:
            self.last_tick = tick
            return

        if self.btc == 0:
            if predicted_change_pct >= self.entry_threshold:
                pred_time = datetime.strptime(forecast_time, '%Y-%m-%d %H:%M:%S') if forecast_time else now
                if (now - pred_time).total_seconds() <= self.prediction_valid_seconds:
                    self.buy(timestamp, trade_price, predicted_price, predicted_change_pct)
                    self.last_prediction = {
                        'predicted_price': predicted_price,
                        'predicted_change_pct': predicted_change_pct
                    }
        else:
            current_profit = ((trade_price - self.buy_price) / self.buy_price) * 100
            sell_reason = None
            if current_profit >= self.exit_threshold:
                sell_reason = "Выход: прибыль >= порога"
            elif current_profit <= -self.exit_threshold and current_profit < 0:
                sell_reason = "Выход: убыток стал отрицательным"
            elif current_profit <= -self.stop_loss_pct:
                sell_reason = "Выход: стоп-лосс"
            elif self.entry_time:
                hold_time = now - self.entry_time
                if hold_time > self.max_hold and current_profit < 0:
                    sell_reason = f"Выход: удержание > {self.max_hold} и убыток"
            elif self.last_mae is not None and self.last_mae > self.mae_stop_threshold and current_profit < 0:
                sell_reason = f"Выход: высокая MAE {self.last_mae:.4f} и убыток"

            if sell_reason:
                self.sell(timestamp, trade_price, self.last_prediction.get('predicted_price') if self.last_prediction else None, predicted_change_pct, reason=sell_reason)
                self.cooldown_until = datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(seconds=self.cooldown_seconds)

        self.last_tick = tick

    def buy(self, timestamp: str, trade_price: float, predicted_price: Optional[float], predicted_change_pct: Optional[float]):
        if self.balance <= 0:
            return

        fee = self.calculate_fee(self.balance)
        net_balance = self.balance - fee
        self.btc = net_balance / trade_price
        self.buy_price = trade_price
        self.cost_basis = self.balance
        self.balance = 0.0
        self.set_stop_loss()
        self.entry_time = datetime.now(ZoneInfo("Europe/Moscow"))
        self.peak_price = trade_price

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
        self.save_session()

    def sell(self, timestamp: str, trade_price: float, predicted_price: Optional[float], predicted_change_pct: Optional[float], reason: str = None):
        if self.btc <= 0:
            return

        proceeds = self.btc * trade_price
        fee = self.calculate_fee(proceeds)
        net_proceeds = proceeds - fee
        profit = net_proceeds - self.cost_basis
        self.balance = net_proceeds

        if reason is None:
            reason = "Выход"

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
        self.save_session()

        self.btc = 0.0
        self.buy_price = 0.0
        self.cost_basis = 0.0
        self.pending_log = None
        self.stop_loss_price = None
        self.entry_time = None
        self.peak_price = None

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