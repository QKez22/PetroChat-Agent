"""One leased graph node per tick; HTTP/SSE lifetimes never own report execution."""

import threading

from langgraph.types import Command
from loguru import logger

from .store import Conflict, LeasedSaver, ReportStore
from .workflow import ArtifactStore, build_report_graph, business_query


class ReportWorker:
    def __init__(self, store: ReportStore, root, query=business_query):
        self.store, self.root, self.query = store, root, query

    def run_once(self):
        task = self.store.claim()
        if task is None:
            return False
        task_id, token = task["id"], task["lease_token"]
        state = dict(task["state_json"])
        config = {"configurable": {"thread_id": f"{task_id}-{state['generation']}"}}
        try:
            graph = build_report_graph(
                LeasedSaver(self.store, task_id, token),
                ArtifactStore(self.store, self.root, task, token),
                self.query,
            )
            before = graph.get_state(config)
            pending = [i for t in before.tasks for i in t.interrupts]
            decision = state.get("decision")
            if not before.values:
                graph.invoke({"question": task["question"]}, config, durability="sync")
            elif pending:
                if decision == pending[0].id:
                    graph.invoke(Command(resume={pending[0].id: True}), config, durability="sync")
            elif before.next:
                graph.invoke(None, config, durability="sync")
            # If a crash happened after checkpoint commit, derive status from graph,
            # not stale task bookkeeping. Never replay approval into a different gate.
            after = graph.get_state(config)
            pending = [i for t in after.tasks for i in t.interrupts]
            state.pop("decision", None)
            state.pop("error", None)
            state.pop("interrupt_id", None)
            state.pop("review", None)
            state["next"] = list(after.next)
            state["artifacts"] = {
                k: after.values[k]
                for k in ("snapshot", "draft", "chart", "export")
                if after.values.get(k)
            }
            if pending:
                state.update(interrupt_id=pending[0].id, review=pending[0].value)
                status = "awaiting_input"
            else:
                status = "queued" if after.next else "completed"
            self.store.finish_step(task_id, token, status, state)
        except Conflict:
            # Cancelled/expired/reclaimed worker is fenced, not allowed to change status.
            logger.info("Report worker fenced: {}", task_id)
        except Exception as exc:
            logger.warning("Report node failed: task={} type={}", task_id, type(exc).__name__)
            state["error"] = "节点执行失败，可重试；连续失败 3 次后需手动恢复。"
            try:
                self.store.finish_step(
                    task_id,
                    token,
                    "failed" if task["attempts"] >= 3 else "queued",
                    state,
                    error=True,
                )
            except Conflict:
                pass
        return True


class ReportWorkerService:
    def __init__(self, worker):
        self.worker = worker
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="report-worker", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.worker.run_once()
            except Exception as exc:
                logger.warning("Report worker unavailable: {}", type(exc).__name__)
            self.stop_event.wait(1)

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)
        # In-flight calls may finish; lease fencing protects restart/reclaim.
