"""Application-owned worker lifecycle; durable jobs survive API restarts."""
import threading
import time

from loguru import logger

from .long_term import get_long_term_memory_store
from .mem0_adapter import get_mem0_memory_adapter
from .sync import MemorySyncWorker


class MemoryWorkerService:
    def __init__(self, worker=None, *, interval=5, repair_interval=300):
        self.worker = worker
        self.interval, self.repair_interval = interval, repair_interval
        self.stop_event = threading.Event()
        self.thread = None
        self.last_result = {}
        self.last_error = ""

    def start(self):
        self.thread = threading.Thread(target=self._run, name="memory-sync", daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _run(self):
        next_repair = 0.0
        while not self.stop_event.is_set():
            try:
                if self.worker is None:
                    self.worker = MemorySyncWorker(get_long_term_memory_store(), get_mem0_memory_adapter())
                if time.monotonic() >= next_repair:
                    next_repair = time.monotonic() + self.repair_interval
                    # Maintenance failures must not starve durable pending writes.
                    for maintenance in (self.worker.reconcile, self.worker.adapter.cleanup_candidates):
                        try:
                            maintenance()
                        except Exception as exc:
                            logger.warning("Memory maintenance deferred: {}", type(exc).__name__)
                self.last_result = self.worker.run_once()
                self.last_error = ""
                if self.last_result.get("failed"):
                    logger.warning("Memory sync pending retries: {}", self.last_result)
            except Exception as exc:
                self.last_error = type(exc).__name__
                logger.warning("Memory worker retrying after {}", self.last_error)
            self.stop_event.wait(self.interval)
