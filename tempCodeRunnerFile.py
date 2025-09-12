import yaml
import threading
from apps.simulation_app.dashboard import TradingDashboard
from apps.logs_app.logs_dashboard import LogsDashboard
from apps.simulation_app.session_manager import SessionManagerDashboard
from utils.logger import setup_logger

logger = setup_logger('main')

# Загружаем конфиг
config = yaml.safe_load(open('config.yaml', 'r'))
env = config.get('env', 'prod')  # По умолчанию prod

def run_simulation_app():
    logger.info(f"Запуск TradingDashboard (порт будет взят из config.yaml: {config['ports'][env]['simulation']})")
    app = TradingDashboard()
    app.run()

def run_logs_app():
    logger.info(f"Запуск LogsDashboard (порт будет взят из config.yaml: {config['ports'][env]['logs']})")
    app = LogsDashboard()
    app.run()

def run_session_manager_app():
    logger.info(f"Запуск SessionManagerDashboard (порт будет взят из config.yaml: {config['ports'][env]['session_manager']})")
    app = SessionManagerDashboard()
    app.run()

if __name__ == '__main__':
    logger.info(f"Запуск приложения в окружении {env}. Порты: simulation={config['ports'][env]['simulation']}, logs={config['ports'][env]['logs']}, session_manager={config['ports'][env]['session_manager']}")
    
    simulation_thread = threading.Thread(target=run_simulation_app, daemon=True)
    logs_thread = threading.Thread(target=run_logs_app, daemon=True)
    session_manager_thread = threading.Thread(target=run_session_manager_app, daemon=True)
    
    simulation_thread.start()
    logs_thread.start()
    session_manager_thread.start()
    
    try:
        simulation_thread.join()
        logs_thread.join()
        session_manager_thread.join()
    except KeyboardInterrupt:
        logger.info("Приложение остановлено пользователем")