from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import create_engine

from petrochat.app.report.persistence import ReportCheckpointSaver, schema


class State(TypedDict):
    snapshot: str
    approved: bool


def make_graph(saver, calls):
    def query(state):
        calls.append("query")
        return {"snapshot": "fixed-snapshot-sha256"}

    def review(state):
        approved = interrupt({"snapshot": state["snapshot"]})
        return {"approved": bool(approved)}

    graph = StateGraph(State)
    graph.add_node("query", query)
    graph.add_node("review", review)
    graph.add_edge(START, "query")
    graph.add_edge("query", "review")
    graph.add_edge("review", END)
    return graph.compile(checkpointer=saver)


def test_interrupt_survives_engine_recreation_without_requery(tmp_path):
    url = f"sqlite:///{tmp_path / 'checkpoint.db'}"
    engine = create_engine(url)
    schema.create_all(engine)
    calls, config = [], {"configurable": {"thread_id": "report-one"}}
    graph = make_graph(ReportCheckpointSaver(engine), calls)
    first = graph.invoke({}, config, durability="sync")
    assert first["__interrupt__"] and calls == ["query"]
    engine.dispose()
    reopened = ReportCheckpointSaver(create_engine(url))
    graph = make_graph(reopened, calls)
    result = graph.invoke(Command(resume=True), config, durability="sync")
    assert result["approved"] and calls == ["query"]
    assert reopened.get_tuple({"configurable": {"thread_id": "other"}}) is None
    history = list(reopened.list(config))
    assert len(history) >= 3 and len(list(reopened.list(config, limit=1))) == 1
    assert list(reopened.list(config, before=history[-1].config)) == []
    assert list(reopened.list(config, filter={"not_a_field": "x"})) == []
    reopened.delete_thread("report-one")
    assert reopened.get_tuple(config) is None


def test_pending_writes_keep_success_but_update_error(tmp_path):
    from langgraph.checkpoint.base import empty_checkpoint

    engine = create_engine(f"sqlite:///{tmp_path / 'writes.db'}")
    schema.create_all(engine)
    saver = ReportCheckpointSaver(engine)
    config = saver.put(
        {"configurable": {"thread_id": "one"}},
        empty_checkpoint(),
        {"source": "input", "step": -1, "parents": {}},
        {},
    )
    saver.put_writes(config, [("snapshot", "first")], "task")
    saver.put_writes(config, [("snapshot", "duplicate")], "task")
    saver.put_writes(config, [("__error__", "old")], "error-task")
    saver.put_writes(config, [("__error__", "new")], "error-task")
    values = {
        (task, channel): value for task, channel, value in saver.get_tuple(config).pending_writes
    }
    assert values[("task", "snapshot")] == "first"
    assert values[("error-task", "__error__")] == "new"
    with pytest.raises(ValueError):
        list(saver.list(None))


def test_resume_in_a_fresh_python_process(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    url = f"sqlite:///{tmp_path / 'process.db'}"
    engine = create_engine(url)
    schema.create_all(engine)
    config = {"configurable": {"thread_id": "restart"}}
    make_graph(ReportCheckpointSaver(engine), []).invoke({}, config, durability="sync")
    engine.dispose()
    code = """
import sys
from sqlalchemy import create_engine
from langgraph.types import Command
from test_report_persistence import make_graph
from petrochat.app.report.persistence import ReportCheckpointSaver
calls = []
graph = make_graph(ReportCheckpointSaver(create_engine(sys.argv[1])), calls)
result = graph.invoke(Command(resume=True), {"configurable":{"thread_id":"restart"}}, durability="sync")
assert result['approved'] and calls == []
print('fresh process resumed without re-query')
"""
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent)}
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, url], env=env, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "fresh process resumed" in result.stdout


def test_report_migration_grants_only_expected_tables():
    import re
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1] / "scripts/migrations/007_report_workflow.sql"
    ).read_text()
    expected = {
        "agent_report_" + name for name in ("task", "event", "artifact", "checkpoint", "write")
    }
    assert set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql)) == expected
    assert (
        set(
            re.findall(
                r"GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task\.(\w+) TO 'petrochat_app'@'%';",
                sql,
            )
        )
        == expected
    )
    assert "ALL PRIVILEGES" not in sql and "ON *" not in sql
