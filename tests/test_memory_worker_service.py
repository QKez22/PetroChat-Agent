import threading
from types import SimpleNamespace

from petrochat.app.memory.worker_service import MemoryWorkerService


def test_service_runs_repair_then_consumes_and_stops():
    done = threading.Event()
    calls = []
    def consume():
        calls.append("consume")
        done.set()
        return {"succeeded":1,"failed":0}
    worker = SimpleNamespace(reconcile=lambda:calls.append("repair"),
        adapter=SimpleNamespace(cleanup_candidates=lambda:calls.append("cleanup")),run_once=consume)
    service = MemoryWorkerService(worker,interval=.01).start()
    try:
        assert done.wait(2)
    finally:
        service.stop()
    assert calls[:3] == ["repair","cleanup","consume"]
    assert not service.thread.is_alive()


def test_maintenance_failure_does_not_starve_queue():
    done = threading.Event()
    def fail():
        raise TimeoutError()
    def consume():
        done.set()
        return {"succeeded": 1, "failed": 0}
    worker = SimpleNamespace(reconcile=fail,
        adapter=SimpleNamespace(cleanup_candidates=fail), run_once=consume)
    service = MemoryWorkerService(worker, interval=.01).start()
    try:
        assert done.wait(2)
    finally:
        service.stop()
