"""Durable single-report graph. Checkpoints contain references, never datasets."""

import base64
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import TypedDict

import pandas as pd
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select

from . import render_report
from .store import artifacts, utcnow


class ReportState(TypedDict, total=False):
    question: str
    plan: str
    plan_approved: bool
    snapshot: str
    draft: str
    chart: str
    draft_approved: bool
    export: str


class ArtifactStore:
    """Immutable content files + fenced manifests. Shared durable volume required."""

    def __init__(self, store, root, task, token):
        self.store, self.root, self.task, self.token = store, Path(root).resolve(), task, token
        self.generation = task["state_json"]["generation"]

    def find(self, kind):
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    select(artifacts).where(
                        artifacts.c.task_id == self.task["id"],
                        artifacts.c.revision == self.generation,
                        artifacts.c.kind == kind,
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def put(self, kind, data: bytes):
        if len(data) > 16 * 1024 * 1024:
            raise ValueError("report artifact exceeds 16 MiB limit")
        digest = hashlib.sha256(data).hexdigest()
        # Server-controlled hash only; no user filenames, atomic publication.
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".report-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.root / digest)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        identity = hashlib.sha256(
            f"{self.task['id']}/{self.generation}/{kind}".encode()
        ).hexdigest()
        with self.store.engine.begin() as conn:
            self.store.fence(conn, self.task["id"], self.token)
            old = (
                conn.execute(select(artifacts).where(artifacts.c.id == identity)).mappings().first()
            )
            if old:
                return old["id"]
            conn.execute(
                artifacts.insert().values(
                    id=identity,
                    task_id=self.task["id"],
                    revision=self.generation,
                    kind=kind,
                    storage_key=digest,
                    sha256=digest,
                    byte_size=len(data),
                    created_at=utcnow(),
                )
            )
        return identity

    def read(self, identity):
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    select(artifacts).where(
                        artifacts.c.id == identity,
                        artifacts.c.task_id == self.task["id"],
                        artifacts.c.revision == self.generation,
                    )
                )
                .mappings()
                .one()
            )
        key = row["storage_key"]
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("invalid artifact key")
        data = (self.root / key).read_bytes()
        if len(data) != row["byte_size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("artifact integrity verification failed")
        return data


def business_query(question):
    from ..sql import nl2sql

    result = nl2sql(question)
    if not result.ok:
        # Avoid persisting credentials/driver exceptions in user-visible state.
        raise RuntimeError(f"report query failed at {result.stage}")
    frame = pd.DataFrame(result.rows, columns=result.columns)
    return {
        "columns": result.columns,
        "rows": json.loads(frame.to_json(orient="records", date_format="iso")),
        "sql": result.sql,
        "captured_at": utcnow().isoformat() + "Z",
        "scope_note": "仅覆盖本次 SQL 返回结果，可能受查询行数上限影响；不代表全库明细。",
    }


def safe_csv(frame):
    def cell(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value

    safe = frame.map(cell)
    safe.columns = [cell(str(c)) for c in safe.columns]
    return safe.to_csv(index=False).encode("utf-8-sig")


def build_report_graph(saver, files, query=business_query):
    def plan(state):
        return {
            "plan": f"统计需求：{state['question']}\n执行只读查询并固定快照；生成图表、结果概览和 ZIP。"
            "\n请在批准前明确时间范围、分组维度和统计口径；如有歧义请修改完整需求。"
        }

    def confirm_plan(state):
        answer = interrupt({"stage": "plan", "text": state["plan"]})
        if answer is not True:
            raise ValueError("explicit approval required")
        return {"plan_approved": True}

    def snapshot(state):
        old = files.find("snapshot")
        if old:
            files.read(old["id"])  # Fail closed on missing/corrupt durable volume.
            return {"snapshot": old["id"]}
        result = query(state["question"])
        if len(result["rows"]) > 10000:
            raise ValueError("report snapshot exceeds 10000 rows")
        return {"snapshot": files.put("snapshot", json.dumps(result, ensure_ascii=False).encode())}

    def draft(state):
        snapshot = json.loads(files.read(state["snapshot"]))
        frame = pd.DataFrame(snapshot["rows"], columns=snapshot["columns"])
        report = render_report(frame, title="业务统计报表", max_rows=50)
        chart = ""
        if report.chart_data_uri:
            chart = files.put("chart", base64.b64decode(report.chart_data_uri.split(",", 1)[1]))
        overview = f"本次快照返回 {len(frame)} 行、{len(frame.columns)} 列。"
        for column in frame.select_dtypes(include="number").columns:
            values = frame[column].dropna()
            if not values.empty:
                overview += f"\n- {column}：最小值 {values.min():g}，最大值 {values.max():g}。"
        markdown = (
            f"# 业务统计报表\n\n需求：{state['question']}\n\n"
            f"快照时间：{snapshot.get('captured_at', 'unknown')}\n\n"
            f"{snapshot.get('scope_note', '仅覆盖本次查询返回结果。')}\n\n"
            f"## 结果概览\n\n{overview}\n\n描述性统计，不推断因果。\n\n"
            f"{report.markdown}\n\n"
            + ("![图表](chart.png)\n\n" if chart else "")
            + f"## 查询溯源\n\n```sql\n{snapshot.get('sql', '')}\n```\n"
        )
        return {"draft": files.put("draft", markdown.encode()), "chart": chart}

    def confirm_draft(state):
        answer = interrupt({"stage": "draft", "artifact_id": state["draft"]})
        if answer is not True:
            raise ValueError("explicit approval required")
        return {"draft_approved": True}

    def export(state):
        old = files.find("export")
        if old:
            files.read(old["id"])
            return {"export": old["id"]}
        snapshot = json.loads(files.read(state["snapshot"]))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("report.md", files.read(state["draft"]))
            archive.writestr(
                "data.csv", safe_csv(pd.DataFrame(snapshot["rows"], columns=snapshot["columns"]))
            )
            archive.writestr(
                "provenance.json",
                json.dumps({k: v for k, v in snapshot.items() if k != "rows"}, ensure_ascii=False),
            )
            if state.get("chart"):
                archive.writestr("chart.png", files.read(state["chart"]))
        return {"export": files.put("export", buffer.getvalue())}

    builder = StateGraph(ReportState)
    nodes = [plan, confirm_plan, snapshot, draft, confirm_draft, export]
    previous = START
    for node in nodes:
        builder.add_node(node.__name__, node)
        builder.add_edge(previous, node.__name__)
        previous = node.__name__
    builder.add_edge(previous, END)
    return builder.compile(checkpointer=saver, interrupt_after="*")
