from datetime import datetime
from typing import List, Dict, Tuple
from utils.logger import setup_logger
from utils.csv_writer import save_to_csv
from zoneinfo import ZoneInfo
import uuid
import os
import re

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
        self.session_id = str(uuid.uuid4())[:4]  # Короткий токен (4 символа UUID)
        self.start_time = datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d_%H-%M-%S')
        self.metadata = {
            'session_id': self.session_id,
            'start_balance': start_balance,
            'entry_threshold': entry_threshold,
            'exit_threshold': exit_threshold,
            'fee_pct': fee_pct,
            'interval': interval,
            'start_time': self.start_time
        }
        logger.info(f"Инициализация симулятора ({interval}): баланс={start_balance}, entry={entry_threshold}%, exit={exit_threshold}%, fee={fee_pct}%, session_id={self.session_id}")
        self.save_session()  # Создаём файл при старте

    def process_tick(self, tick: Dict):
        """Обрабатывает тиковую информацию"""
        actual_price = tick['actual_price']
        prediction = tick['predictions'].get(self.interval)
        if not prediction:
            logger.warning(f"Прогноз для интервала {self.interval} отсутствует")
            return

        pred_value, change_pct, _ = prediction
        msk_time = datetime.now(ZoneInfo("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')

        if self.btc == 0:  # Нет позиции
            if change_pct >= self.entry_threshold:
                self.buy(actual_price, msk_time)
        else:  # Есть позиции
            current_change = (actual_price - self.buy_price) / self.buy_price
            if current_change >= self.exit_threshold or change_pct < 0:
                self.sell(actual_price, msk_time)

    def buy(self, price: float, timestamp: str):
        """Покупка BTC"""
        if self.balance <= 0:
            logger.warning("Недостаточно средств для покупки")
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
        self.save_session()  # Сохраняем после покупки

    def sell(self, price: float, timestamp: str):
        """Продажа BTC"""
        if self.btc <= 0:
            logger.warning("Нет BTC для продажи")
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
        self.save_session()  # Сохраняем после продажи

        self.btc = 0
        self.buy_price = 0

    def get_trade_log(self) -> List[Dict]:
        return self.trade_log

    def get_balance_series(self) -> List[Tuple[str, float]]:
        return self.balance_series

    def get_total_profit(self) -> float:
        """Возвращает суммарную прибыль за сессию"""
        return sum(log.get('profit', 0) for log in self.trade_log)

    def get_current_btc(self) -> float:
        """Возвращает текущее количество BTC"""
        return self.btc

    def get_current_balance(self) -> float:
        """Возвращает текущий баланс в USDT"""
        return self.balance

    def save_session(self):
        """Сохраняет текущую сессию в CSV"""
        logger.info(f"Сохранение сессии, trade_log содержит {len(self.trade_log)} записей")
        base_filename = f"simulations/simulation_{self.start_time}_{self.session_id}_{self.interval}.csv"
        filename = base_filename
        suffix = 1
        while os.path.exists(filename):
            logger.warning(f"Файл {filename} уже существует, добавляем суффикс _{suffix}")
            filename = base_filename.replace(f".csv", f"_{suffix}.csv")
            suffix += 1
        save_to_csv(self.trade_log, self.metadata, filename)