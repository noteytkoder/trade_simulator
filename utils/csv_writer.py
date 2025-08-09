import csv
import os
from typing import List, Dict
from utils.logger import setup_logger

logger = setup_logger('csv_writer')

def save_to_csv(trade_log: List[Dict], metadata: Dict, filename: str):
    """Сохраняет логи торговли в CSV с метаданными."""
    try:
        logger.debug(f"Сохранение в CSV: {filename}, {len(trade_log)} записей")
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            # Записываем метаданные как комментарии
            for key, value in metadata.items():
                f.write(f"# {key}: {value}\n")
            f.write("\n")
            # Записываем логи с явным указанием всех полей
            if trade_log:
                fieldnames = [
                    'timestamp', 'type', 'price', 'amount', 'fee', 'balance', 'profit',
                    'actual_price', 'predicted_price', 'predicted_change_pct', 'reason', 'prediction_accuracy'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                for row in trade_log:
                    row = {
                        **row,
                        'profit': row.get('profit', ''),
                        'actual_price': row.get('actual_price', ''),
                        'predicted_price': row.get('predicted_price', ''),
                        'predicted_change_pct': row.get('predicted_change_pct', ''),  # Сохраняем как есть
                        'reason': row.get('reason', ''),
                        'prediction_accuracy': row.get('prediction_accuracy', '')
                    }
                    writer.writerow(row)
            else:
                logger.warning("trade_log пуст, записываются только метаданные")
        logger.info(f"Сохранено в CSV: {filename}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении в CSV {filename}: {e}")

def update_csv_accuracy(trade_log: List[Dict], metadata: Dict, filename: str, pending_log: Dict):
    """Обновляет последнюю запись в CSV с актуальной точностью прогноза."""
    try:
        logger.debug(f"Обновление CSV: {filename}, последняя запись: {pending_log}")
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            # Перезаписываем метаданные
            for key, value in metadata.items():
                f.write(f"# {key}: {value}\n")
            f.write("\n")
            # Перезаписываем весь лог
            fieldnames = [
                'timestamp', 'type', 'price', 'amount', 'fee', 'balance', 'profit',
                'actual_price', 'predicted_price', 'predicted_change_pct', 'reason', 'prediction_accuracy'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for row in trade_log:
                row = {
                    **row,
                    'profit': row.get('profit', ''),
                    'actual_price': row.get('actual_price', ''),
                    'predicted_price': row.get('predicted_price', ''),
                    'predicted_change_pct': row.get('predicted_change_pct', ''),  # Сохраняем как есть
                    'reason': row.get('reason', ''),
                    'prediction_accuracy': row.get('prediction_accuracy', '')
                }
                writer.writerow(row)
        logger.info(f"CSV успешно обновлён: {filename}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении CSV {filename}: {e}")