import requests
from bs4 import BeautifulSoup
from typing import Dict
from utils.logger import setup_logger
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import re

logger = setup_logger('parser')

class TableParser:
    @staticmethod
    def fetch(url: str, auth: tuple = None) -> str:
        """Скачивает HTML-страницу по URL с повторными попытками."""
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[404, 500, 502, 503, 504])
        session.mount('http://', HTTPAdapter(max_retries=retries))
        try:
            resp = session.get(url, auth=auth, timeout=5)
            resp.raise_for_status()
            # logger.info(f"Успешно получены данные с {url}")
            return resp.text
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении данных с {url}: {e}")
            raise

    @staticmethod
    def parse(html: str, interval: str = None) -> Dict:
        """
        Извлекает из HTML-таблицы последнюю строку.
        Возвращает словарь с полями:
          - timestamp: str (время факта)
          - actual_price: float
          - predictions: dict<model_name, (value, change_pct, forecast_time)>
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table')
            if not table:
                logger.error("Таблица не найдена в HTML")
                raise ValueError("Таблица не найдена")

            rows = table.find('tbody').find_all('tr')
            if not rows:
                logger.error("Строки в таблице отсутствуют")
                raise ValueError("Строки в таблице отсутствуют")

            last_row = rows[-1]
            cells = last_row.find_all('td')

            timestamp = cells[0].text.strip()
            actual_price = float(cells[1].text.strip())

            if interval == '5s':
                pred_text = cells[2].text.strip().split('(')
                pred_value = float(pred_text[0].strip())
                change_and_time = pred_text[1].split(')')[0].strip() + pred_text[1].split(')')[1].strip()

                change_match = re.search(r'[+-]?\d*\.\d+%?', change_and_time)
                if not change_match:
                    raise ValueError("Неверный формат процента изменения")
                change_pct = float(change_match.group().replace('%', '')) / 100

                time_match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', change_and_time)
                if not time_match:
                    raise ValueError("Неверный формат времени прогноза")
                pred_time = time_match.group()

                return {
                    'timestamp': timestamp,
                    'actual_price': actual_price,
                    'predictions': {
                        '5s': (pred_value, change_pct, pred_time)
                    }
                }
            else:
                min_pred_text = cells[2].text.strip().split('(')
                min_pred = float(min_pred_text[0].strip())
                min_change_and_time = min_pred_text[1].split(')')[0].strip() + min_pred_text[1].split(')')[1].strip()
                min_change_match = re.search(r'[+-]?\d*\.\d+%?', min_change_and_time)
                min_change = float(min_change_match.group().replace('%', '')) / 100
                min_time = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', min_change_and_time).group()

                hour_pred_text = cells[3].text.strip().split('(')
                hour_pred = float(hour_pred_text[0].strip())
                hour_change_and_time = hour_pred_text[1].split(')')[0].strip() + hour_pred_text[1].split(')')[1].strip()
                hour_change = float(re.search(r'[+-]?\d*\.\d+%?', hour_change_and_time).group().replace('%', '')) / 100
                hour_time = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', hour_change_and_time).group()

                return {
                    'timestamp': timestamp,
                    'actual_price': actual_price,
                    'predictions': {
                        '1m': (min_pred, min_change, min_time),
                        '1h': (hour_pred, hour_change, hour_time)
                    }
                }

        except Exception as e:
            logger.error(f"Ошибка парсинга HTML: {e}")
            raise