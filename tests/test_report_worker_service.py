import threading

from petrochat.app.report.worker import ReportWorkerService


def test_worker_lifecycle_runs_and_stops():
    ran = threading.Event()

    class Worker:
        def run_once(self):
            ran.set()

    service = ReportWorkerService(Worker()).start()
    assert ran.wait(3)
    service.stop()
    assert not service.thread.is_alive()
