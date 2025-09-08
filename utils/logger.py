import logging
import os
from concurrent_log_handler import ConcurrentRotatingFileHandler

def setup_logger(name: str, log_file: str = 'simulator.log', max_bytes: int = 10485760, backup_count: int = 10) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Форматтер
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Ротирующий файловый хендлер с поддержкой многопоточности
    file_handler = ConcurrentRotatingFileHandler(
        log_file,
        maxBytes=max_bytes,  # Максимальный размер файла в байтах (10 МБ)
        backupCount=backup_count,  # Количество резервных файлов
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Очищаем существующие хендлеры и добавляем только ротирующий
    logger.handlers = []
    logger.addHandler(file_handler)

    return logger