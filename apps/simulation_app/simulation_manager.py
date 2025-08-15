import threading
import time
from datetime import datetime
import yaml
from trading.simulator import TradeSimulator
from utils.parser import TableParser
from utils.logger import setup_logger
import logging

logger = setup_logger('simulation_manager')

class SimulationManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SimulationManager, cls).__new__(cls)
            cls._instance._init_once()
        logger.debug(f"Singleton SimulationManager возвращён, экземпляр адрес: {id(cls._instance)}")
        return cls._instance

    def _init_once(self):
        self.config = yaml.safe_load(open('config.yaml', 'r'))
        logger.setLevel(getattr(logging, self.config.get('log_level', 'INFO')))
        self.auth = (self.config['auth']['username'], self.config['auth']['password'])
        self.simulations = {}
        self.current_price = None
        self.lock = threading.Lock()
        logger.info(f"Singleton SimulationManager создан, экземпляр адрес: {id(self)}, simulations адрес: {id(self.simulations)}")

    def start_simulation(self, interval, balance, entry_threshold, exit_threshold, fee) -> str:
        session_id = f"{interval}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with self.lock:
            logger.debug(f"Начало создания сессии {session_id} для {interval}. Экземпляр: {id(self)}, simulations: {id(self.simulations)}")
            if interval not in self.simulations:
                self.simulations[interval] = {}
            sim = TradeSimulator(balance, entry_threshold, exit_threshold, fee, interval, session_id)
            thread = threading.Thread(target=self._run_loop, args=(sim, session_id), daemon=True)
            self.simulations[interval][session_id] = {
                "thread": thread,
                "sim": sim,
                "running": True,
                "paused": False
            }
            thread.start()
            logger.info(f"Сессия {session_id} запущена для интервала {interval}. Текущее хранение: {len(self.simulations)} интервалов, {len(self.simulations.get(interval, {}))} сессий, simulations адрес: {id(self.simulations)}")
        return session_id

    def stop_simulation(self, interval, session_id):
        with self.lock:
            logger.debug(f"Начало остановки сессии {session_id} для {interval}. Экземпляр: {id(self)}, simulations: {id(self.simulations)}")
            if interval in self.simulations and session_id in self.simulations[interval]:
                self.simulations[interval][session_id]["running"] = False
                self.simulations[interval][session_id]["sim"].save_session()
                logger.info(f"Сессия {session_id} остановлена. Сохранено в CSV. Хранение перед удалением: {len(self.simulations.get(interval, {}))} сессий в {interval}, simulations адрес: {id(self.simulations)}")
                del self.simulations[interval][session_id]
                if not self.simulations[interval]:
                    del self.simulations[interval]
            else:
                logger.warning(f"Сессия {session_id} не найдена для остановки в {interval}. Текущее хранение: {self.simulations.get(interval, 'пусто')}, simulations адрес: {id(self.simulations)}")

    def pause_simulation(self, interval, session_id, pause: bool):
        with self.lock:
            if interval in self.simulations and session_id in self.simulations[interval]:
                self.simulations[interval][session_id]["paused"] = pause
                logger.info(f"Сессия {session_id} {'приостановлена' if pause else 'возобновлена'}. Текущее состояние: paused={pause}, running={self.simulations[interval][session_id]['running']}, simulations адрес: {id(self.simulations)}")
            else:
                logger.warning(f"Сессия {session_id} не найдена для паузы в {interval}. Текущее хранение: {self.simulations.get(interval, 'пусто')}, simulations адрес: {id(self.simulations)}")

    def _run_loop(self, sim: TradeSimulator, session_id: str):
        interval = sim.interval
        poll_interval = self.config['poll_intervals'].get(interval, 5)
        logger.info(f"Запуск потока для сессии {session_id} с интервалом {interval}. Экземпляр: {id(self)}, simulations: {id(self.simulations)}")
        try:
            while True:
                with self.lock:
                    if interval not in self.simulations or session_id not in self.simulations[interval]:
                        logger.warning(f"Сессия {session_id} удалена из хранения во время выполнения потока. Завершаем цикл. Текущее хранение: {self.simulations.get(interval, 'пусто')}, simulations адрес: {id(self.simulations)}")
                        break
                    if not self.simulations[interval][session_id]["running"]:
                        logger.info(f"Сессия {session_id} остановлена, завершаем поток. simulations адрес: {id(self.simulations)}")
                        break
                    paused = self.simulations[interval][session_id]["paused"]
                if paused:
                    time.sleep(1)
                    continue
                try:
                    endpoint = (
                        self.config['endpoints']['five_sec']
                        if interval == '5s'
                        else self.config['endpoints']['minute_hour']
                    )
                    html_content = TableParser.fetch(endpoint, self.auth)
                    tick = TableParser.parse(html_content, interval)
                    if tick:
                        self.current_price = tick['actual_price']
                        sim.process_tick(tick)
                except Exception as e:
                    logger.error(f"Ошибка в цикле симуляции ({interval}, сессия {session_id}): {e}. Продолжаем работу, сессия не удаляется.")
                time.sleep(poll_interval)
            logger.info(f"Поток для сессии {session_id} завершён корректно. simulations адрес: {id(self.simulations)}")
        except Exception as e:
            logger.error(f"Критическая ошибка в потоке ({interval}, сессия {session_id}): {e}. Сессия не удаляется.")

    def get_simulator(self, interval, session_id):
        with self.lock:
            sim = self.simulations.get(interval, {}).get(session_id, {}).get("sim")
            if sim:
                logger.info(f"Сессия {session_id} подгружена из памяти для {interval}. Параметры: {sim.metadata}. Экземпляр: {id(self)}, simulations: {id(self.simulations)}, содержание: {self.simulations.get(interval, 'пусто')}")
            else:
                logger.warning(f"Сессия {session_id} не найдена в памяти для {interval}. Экземпляр: {id(self)}, simulations: {id(self.simulations)}, содержание: {self.simulations.get(interval, 'пусто')}")
            return sim

    def list_sessions(self) -> list[dict]:
        sessions = []
        with self.lock:
            for interval, sess_dict in self.simulations.items():
                for session_id, data in sess_dict.items():
                    sim = data["sim"]
                    sessions.append({
                        "interval": interval,
                        "session_id": session_id,
                        "balance": sim.get_current_balance(),
                        "btc": sim.get_current_btc(),
                        "profit": sim.get_total_profit(),
                        "accuracy": sim.get_prediction_accuracy(),
                        "running": data["running"],
                        "paused": data["paused"],
                        "start_time": sim.start_time,
                        "entry_threshold": sim.entry_threshold,
                        "exit_threshold": sim.exit_threshold,
                        "fee_pct": sim.fee_pct
                    })
            logger.info(f"Список сессий возвращён: {len(sessions)} активных сессий. Экземпляр: {id(self)}, simulations: {id(self.simulations)}, хранение: {self.simulations.keys()}")
        return sessions

    def get_current_price(self):
        return self.current_price