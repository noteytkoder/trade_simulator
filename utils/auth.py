import yaml
import os
from utils.logger import setup_logger

logger = setup_logger('auth')

def load_auth_config():
    """Загружает конфигурацию авторизации из auth.yaml."""
    try:
        with open('auth.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {'auth': {'username': 'admin', 'password': 'qwerty63'}}
    except Exception as e:
        logger.error(f"Ошибка чтения auth.yaml: {e}")
        return {'auth': {'username': 'admin', 'password': 'qwerty63'}}

def verify_credentials(username: str, password: str) -> bool:
    """Проверяет логин и пароль."""
    config = load_auth_config()
    return username == config['auth']['username'] and password == config['auth']['password']

def update_password(new_password: str):
    """Обновляет пароль в auth.yaml."""
    try:
        config = load_auth_config()
        config['auth']['password'] = new_password
        with open('auth.yaml', 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
        logger.info("Пароль успешно обновлен")
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении пароля: {e}")
        return False