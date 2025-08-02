from threading import Thread
from apps.simulation_app.dashboard import TradingDashboard
from apps.logs_app.logs_dashboard import LogsDashboard

def run_simulation_app():
    app = TradingDashboard()
    app.run(port=8060)

def run_logs_app():
    app = LogsDashboard()
    app.run(port=8061)

if __name__ == "__main__":
    t1 = Thread(target=run_simulation_app)
    t2 = Thread(target=run_logs_app)

    t1.start()
    t2.start()

    t1.join()
    t2.join()