import requests
from bs4 import BeautifulSoup

class TableParser:
    @staticmethod
    def fetch(url: str) -> str:
        """Скачивает HTML-страницу по URL и возвращает как текст"""
        # TODO: обработка ошибок сети
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def parse(html: str) -> dict:
        """
        Извлекает из HTML-таблицы последнюю строку.
        Возвращает словарь с полями:
          - timestamp
          - actual_price
          - predictions: dict<model_name, (value, change_pct, time)>
        """
        # TODO: реализовать универсальный парсинг через BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        # TODO: найти все строки <tr>, пропустить заголовок
        # TODO: взять последнюю строку и все <td>
        # TODO: распарсить содержимое по колонкам
        return {
            'timestamp': ...,          # str
            'actual_price': ...,       # float
            'predictions': {           # пример:
                'fivesec': (0.0234, +0.12, '2025-07-27 12:34:56'),
                '1min': (...),
                '1h': (...)
            }
        }