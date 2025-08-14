import pandas as pd
import os
from utils.logger import setup_logger

logger = setup_logger('csv_writer')

def save_to_csv(trade_log: list[dict], metadata: dict, filename: str):
    """Сохранение лога торгов в CSV с экранированием значений"""
    if not trade_log:
        logger.warning(f"Попытка сохранить пустой trade_log в {filename}")
        return
    try:
        df = pd.DataFrame(trade_log)
        # Экранируем значения, чтобы избежать проблем с запятыми
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace(',', '\\,')
        df = pd.concat([pd.DataFrame([metadata]), df], ignore_index=True)
        logger.debug(f"Сохранение в CSV {filename}: {df.to_dict()}")
        df.to_csv(filename, index=False, escapechar='\\')
        logger.info(f"Сохранено в CSV: {filename}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении в CSV {filename}: {e}")

def update_csv_accuracy(trade_log: list[dict], metadata: dict, filename: str, pending_log: dict):
    """Обновление CSV с учётом точности прогноза"""
    if not trade_log:
        logger.warning(f"Попытка обновить пустой trade_log в {filename}")
        return
    try:
        df = pd.DataFrame(trade_log)
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace(',', '\\,')
        df = pd.concat([pd.DataFrame([metadata]), df], ignore_index=True)
        logger.debug(f"Обновление CSV {filename}: {df.to_dict()}")
        df.to_csv(filename, index=False, escapechar='\\')
        logger.info(f"CSV успешно обновлён: {filename}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении CSV {filename}: {e}")