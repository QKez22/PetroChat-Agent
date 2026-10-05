"""Real MySQL + NL2SQL acceptance with a fresh-process resume, isolated UUID only.

Runs a real model call and read-only business query; does not touch other jobs.
Test report records are removed; artifacts/evidence retained in data/runtime.
"""

import argparse
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from time import monotonic

from sqlalchemy import delete

from petrochat.app.core.config import PROJECT_ROOT
from petrochat.app.report.persistence import checkpoints, writes_table
from petrochat.app.report.store import ReportStore, artifacts, events, tasks
from petrochat.app.report.worker import ReportWorker
from petrochat.app.report.workflow import ArtifactStore, business_query
from petrochat.app.sql.engine import get_app_engine


def advance(worker, store, task_id, target):
    for _ in range(15):
        row = store.get(task_id, "0")
        if row["status"] == target:
            return row
        if row["status"] == "failed" or row["state_json"].get("error"):
            raise RuntimeError("acceptance node failed; inspect local logs")
        worker.run_once()
    raise RuntimeError(f"acceptance did not reach {target}")


def resume(task_id, root):
    store = ReportStore(get_app_engine())
    row = store.get(task_id, "0")
    assert row["status"] == "paused"

    def no_requery(question):
        raise AssertionError("completed query must not execute after restart")

    store.action(task_id, "0", row["revision"], "resume")
    worker = ReportWorker(store, root, no_requery, task_id=task_id)
    draft = advance(worker, store, task_id, "awaiting_input")
    assert draft["state_json"]["review"]["stage"] == "draft"
    store.action(task_id, "0", draft["revision"], "approve")
    completed = advance(worker, store, task_id, "completed")
    files = ArtifactStore(store, root, completed, "")
    data = files.read(completed["state_json"]["artifacts"]["export"])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert {"report.md", "data.csv", "provenance.json"} <= set(archive.namelist())
        assert archive.testzip() is None
        snapshot = json.loads(files.read(completed["state_json"]["artifacts"]["snapshot"]))
        summary = dict(
            status="completed",
            fresh_process_resume=True,
            query_replayed=False,
            rows=len(snapshot["rows"]),
            files=archive.namelist(),
            export_bytes=len(data),
        )
    print(json.dumps(summary))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume")
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.resume:
        resume(args.resume, args.root)
        return
    engine = get_app_engine()
    store = ReportStore(engine)
    row = store.create("0", "统计各专业的事务数量，按数量降序排列")
    task_id = row["id"]
    root = PROJECT_ROOT / "data" / "runtime" / "report-acceptance" / task_id
    started = monotonic()
    try:
        worker = ReportWorker(store, root, business_query, task_id=task_id)
        plan = advance(worker, store, task_id, "awaiting_input")
        assert plan["state_json"]["review"]["stage"] == "plan"
        store.action(task_id, "0", plan["revision"], "approve")
        worker.run_once()  # approval node
        worker.run_once()  # live query, snapshot, checkpoint
        snapshot = store.get(task_id, "0")
        assert snapshot["state_json"].get("artifacts", {}).get("snapshot"), "live query failed"
        store.action(task_id, "0", snapshot["revision"], "pause")
        engine.dispose()
        result = subprocess.run(
            [sys.executable, __file__, "--resume", task_id, "--root", str(root)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        summary.update(elapsed_seconds=round(monotonic() - started, 2), task_id=task_id)
        (root / "acceptance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    finally:
        with engine.begin() as conn:
            for table, column, value in [
                (writes_table, writes_table.c.thread_id, task_id + "-0"),
                (checkpoints, checkpoints.c.thread_id, task_id + "-0"),
                (artifacts, artifacts.c.task_id, task_id),
                (events, events.c.task_id, task_id),
                (tasks, tasks.c.id, task_id),
            ]:
                conn.execute(delete(table).where(column == value))
        print("Cleaned only acceptance UUID database records; local artifacts retained:", root)


if __name__ == "__main__":
    main()
