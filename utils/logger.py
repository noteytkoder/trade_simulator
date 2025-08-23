import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name: str, log_file: str = 'simulator.log', max_bytes: int = 10485760, backup_count: int = 5) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Форматтер
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Ротирующий файловый хендлер
    file_handler = RotatingFileHandler(
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