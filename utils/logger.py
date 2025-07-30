import logging
import os

def setup_logger(name: str, log_file: str = 'simulator.log') -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Форматтер
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Файловый хендлер
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Очищаем существующие хендлеры и добавляем только файловый
    logger.handlers = []
    logger.addHandler(file_handler)

    return logger