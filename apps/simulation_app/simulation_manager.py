import threading
import time
import yaml
from trading.simulator import TradeSimulator
from utils.parser import TableParser
from utils.logger import setup_logger

logger = setup_logger('simulation_manager')

class SimulationManager:
    def __init__(self):
        self.config = yaml.safe_load(open('config.yaml', 'r'))
        self.auth = (self.config['auth']['username'], self.config['auth']['password'])
        self.simulations = {}  # {interval: {"thread": ..., "sim": ..., "running": bool}}

    def start_simulation(self, interval, balance, entry_threshold, exit_threshold, fee):
        if interval in self.simulations and self.simulations[interval]["running"]:
            logger.warning(f"Симуляция {interval} уже запущена")
            return

        sim = TradeSimulator(balance, entry_threshold, exit_threshold, fee, interval)
        self.simulations[interval] = {
            "thread": threading.Thread(target=self._run_loop, args=(sim,), daemon=True),
            "sim": sim,
            "running": True
        }
        self.simulations[interval]["thread"].start()
        logger.info(f"Симуляция {interval} запущена в отдельном потоке")

    def stop_simulation(self, interval):
        if interval in self.simulations:
            self.simulations[interval]["running"] = False
            self.simulations[interval]["sim"].save_session()
            logger.info(f"Симуляция {interval} остановлена")
        else:
            logger.warning(f"Симуляция {interval} не найдена")

    def _run_loop(self, sim: TradeSimulator):
        interval = sim.interval
        poll_interval = self.config['poll_intervals'].get(interval, 5)
        while self.simulations.get(interval, {}).get("running", False):
            try:
                endpoint = (
                    self.config['endpoints']['five_sec']
                    if interval == '5s'
                    else self.config['endpoints']['minute_hour']
                )
                html_content = TableParser.fetch(endpoint, self.auth)
                tick = TableParser.parse(html_content, interval)
                if tick:
                    sim.process_tick(tick)
            except Exception as e:
                logger.error(f"Ошибка в цикле симуляции ({interval}): {e}")
            time.sleep(poll_interval)

    def get_simulator(self, interval):
        """Возвращает объект симулятора для чтения данных"""
        return self.simulations.get(interval, {}).get("sim")
