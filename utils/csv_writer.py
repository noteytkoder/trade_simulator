import csv
from utils.logger import setup_logger

logger = setup_logger('csv_writer')

def save_to_csv(trade_log: list[dict], metadata: dict, filename: str):
    """Сохраняет логи торговли в CSV с метаданными."""
    if not trade_log:
        logger.warning(f"Попытка сохранить пустой trade_log в {filename}")
        return
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            # Метаданные как комментарии
            for key, value in metadata.items():
                f.write(f"# {key}: {value}\n")
            # Заголовок и данные
            fieldnames = ['timestamp', 'type', 'price', 'amount', 'fee', 'balance', 'profit',
                          'actual_price', 'predicted_price', 'predicted_change_pct', 'reason', 'prediction_accuracy']
            writer = csv.DictWriter(f, fieldnames=fieldnames, escapechar='\\')
            writer.writeheader()
            for row in trade_log:
                writer.writerow(row)
        logger.info(f"Сохранено в CSV: {filename}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении в CSV {filename}: {e}")

def update_csv_accuracy(trade_log: list[dict], metadata: dict, filename: str, pending_log: dict):
    # Аналогично save_to_csv, но обновляем только если pending_log changed
    save_to_csv(trade_log, metadata, filename)  # Простой перезапись, так как лог мал