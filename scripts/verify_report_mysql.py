"""Opt-in MySQL CRUD/checkpoint smoke test; only cleans this run's UUID records."""

from uuid import uuid4

from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import delete, select

from petrochat.app.report.persistence import checkpoints, writes_table
from petrochat.app.report.store import LeasedSaver, ReportStore, artifacts, events, tasks, utcnow
from petrochat.app.sql.engine import get_app_engine


def main():
    engine = get_app_engine()
    store = ReportStore(engine)
    # Deliberately do NOT claim(): this must never pick up a real queued task.
    row = store.create("0", "isolated report migration verification")
    task_id, token = row["id"], uuid4().hex
    try:
        from time import time

        with engine.begin() as conn:
            conn.execute(
                tasks.update()
                .where(tasks.c.id == task_id)
                .values(status="running", lease_token=token, lease_until=time() + 60)
            )
            conn.execute(
                artifacts.insert().values(
                    id=task_id,
                    task_id=task_id,
                    revision=0,
                    kind="snapshot",
                    storage_key="smoke-no-file",
                    sha256="0" * 64,
                    byte_size=0,
                    created_at=utcnow(),
                )
            )
            conn.execute(artifacts.update().where(artifacts.c.id == task_id).values(byte_size=1))
            assert (
                conn.execute(
                    select(artifacts.c.byte_size).where(artifacts.c.id == task_id)
                ).scalar_one()
                == 1
            )
        saver = LeasedSaver(store, task_id, token)
        config = saver.put({"configurable": {"thread_id": task_id}}, empty_checkpoint(), {}, {})
        saver.put_writes(config, [("smoke", "persisted")], "smoke")
        assert saver.get_tuple(config).pending_writes[0][2] == "persisted"
        store.finish_step(task_id, token, "completed", {"generation": 0})
        assert store.get(task_id, "0")["status"] == "completed"
        assert len(store.history(task_id, "0")) == 2
        print("PASS: live MySQL task/event/artifact CRUD and checkpoint/pending-write roundtrip")
    finally:
        with engine.begin() as conn:
            for table, column in [
                (writes_table, writes_table.c.thread_id),
                (checkpoints, checkpoints.c.thread_id),
                (artifacts, artifacts.c.task_id),
                (events, events.c.task_id),
                (tasks, tasks.c.id),
            ]:
                conn.execute(delete(table).where(column == task_id))
        print("Cleaned only this run's UUID records:", task_id)


if __name__ == "__main__":
    main()
