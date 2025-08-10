from threading import Thread
from apps.simulation_app.dashboard import TradingDashboard
from apps.logs_app.logs_dashboard import LogsDashboard
import yaml  # Импорт для чтения конфига

# Загружаем конфиг
config = yaml.safe_load(open('config.yaml', 'r'))
env = config.get('env', 'prod')  # По умолчанию dev

def run_simulation_app():
    app = TradingDashboard()
    app.run(port=config['ports'][env]['simulation'])  # Порт из конфига

def run_logs_app():
    app = LogsDashboard()
    app.run(port=config['ports'][env]['logs'])  # Порт из конфига

if __name__ == "__main__":
    t1 = Thread(target=run_simulation_app)
    t2 = Thread(target=run_logs_app)

    t1.start()
    t2.start()

    t1.join()
    t2.join()