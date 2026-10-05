"""Owner-scoped task repository; task changes and audit events commit together."""

from datetime import datetime, timezone
from time import time
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Table,
    Text,
    select,
    update,
)

from .contracts import WORKFLOW_VERSION
from .persistence import ReportCheckpointSaver, schema

tasks = Table(
    "agent_report_task",
    schema,
    Column("id", String(64), primary_key=True),
    Column("user_id", BigInteger, nullable=False),
    Column("workflow_version", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("question", Text, nullable=False),
    Column("state_json", JSON, nullable=False),
    Column("lease_token", String(64), nullable=False),
    Column("lease_until", Float, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("due_at", Float, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
events = Table(
    "agent_report_event",
    schema,
    Column(
        "id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    ),
    Column("task_id", String(64), nullable=False),
    Column("user_id", BigInteger, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime, nullable=False),
)
artifacts = Table(
    "agent_report_artifact",
    schema,
    Column("id", String(64), primary_key=True),
    Column("task_id", String(64), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("kind", String(32), nullable=False),
    Column("storage_key", String(255), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("byte_size", BigInteger, nullable=False),
    Column("created_at", DateTime, nullable=False),
)


class Conflict(ValueError):
    pass


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ReportStore:
    def __init__(self, engine):
        self.engine = engine

    def create(self, user_id: str, question: str):
        row = dict(
            id=uuid4().hex,
            user_id=int(user_id),
            workflow_version=WORKFLOW_VERSION,
            status="queued",
            revision=0,
            question=question,
            state_json={"generation": 0},
            lease_token="",
            lease_until=0,
            attempts=0,
            due_at=0,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        with self.engine.begin() as conn:
            conn.execute(tasks.insert().values(**row))
            self._event(conn, row, "created", {})
        return row

    def get(self, task_id, user_id):
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(tasks).where(tasks.c.id == task_id, tasks.c.user_id == int(user_id))
                )
                .mappings()
                .first()
            )
        if row is None:
            raise KeyError("report not found")
        return dict(row)

    def list(self, user_id):
        with self.engine.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    select(tasks)
                    .where(tasks.c.user_id == int(user_id))
                    .order_by(tasks.c.created_at.desc())
                    .limit(100)
                ).mappings()
            ]

    def history(self, task_id, user_id, after=0):
        self.get(task_id, user_id)
        with self.engine.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    select(events)
                    .where(events.c.task_id == task_id, events.c.id > after)
                    .order_by(events.c.id)
                    .limit(200)
                ).mappings()
            ]

    def _event(self, conn, row, kind, payload):
        conn.execute(
            events.insert().values(
                task_id=row["id"],
                user_id=row["user_id"],
                revision=row["revision"],
                event_type=kind,
                payload=payload,
                created_at=utcnow(),
            )
        )

    def _update(self, conn, row, kind, **changes):
        changes.update(revision=row["revision"] + 1, updated_at=utcnow())
        result = conn.execute(
            update(tasks)
            .where(tasks.c.id == row["id"], tasks.c.revision == row["revision"])
            .values(**changes)
        )
        if result.rowcount != 1:
            raise Conflict("report changed; refresh and retry")
        row = {**row, **changes}
        self._event(conn, row, kind, {"status": row["status"]})
        return row

    def action(self, task_id, user_id, revision, action, comment=""):
        with self.engine.begin() as conn:
            row = (
                conn.execute(
                    select(tasks)
                    .where(tasks.c.id == task_id, tasks.c.user_id == int(user_id))
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise KeyError("report not found")
            if row["revision"] != revision:
                raise Conflict("report changed; refresh and retry")
            status, state = row["status"], dict(row["state_json"])
            changes = {}
            if action == "cancel" and status not in {"completed", "cancelled"}:
                target = "cancelled"
                changes.update(lease_token="", lease_until=0)
            elif action == "pause" and status in {"queued", "running"}:
                target = "paused" if status == "queued" else "pause_requested"
            elif action == "resume" and status in {"paused", "failed"}:
                target = "queued"
                changes.update(attempts=0, due_at=0, lease_token="", lease_until=0)
            elif action == "approve" and status == "awaiting_input":
                state["decision"] = state["interrupt_id"]
                target = "queued"
            elif action == "revise" and status in {"awaiting_input", "paused", "failed"}:
                question = comment.strip()
                if len(question) < 3:
                    raise Conflict("revision requires a complete report question")
                state = {"generation": state["generation"] + 1}
                changes.update(
                    question=question, attempts=0, due_at=0, lease_token="", lease_until=0
                )
                target = "queued"
            else:
                raise Conflict("action is not allowed in current status")
            return self._update(conn, row, action, status=target, state_json=state, **changes)

    def claim(self, lease_seconds=300, *, task_id=None):
        now = time()
        with self.engine.begin() as conn:
            query = (
                select(tasks)
                .where(
                    tasks.c.status.in_(["queued", "running", "pause_requested"]),
                    tasks.c.lease_until <= now,
                    tasks.c.due_at <= now,
                    tasks.c.workflow_version == WORKFLOW_VERSION,
                )
                .order_by(tasks.c.created_at)
                .limit(1)
            )
            if task_id is not None:
                query = query.where(tasks.c.id == task_id)
            row = conn.execute(query.with_for_update(skip_locked=True)).mappings().first()
            if row is None:
                return None
            # A crashed final attempt becomes visible as failed, never loops forever.
            if row["attempts"] >= 3:
                self._update(
                    conn, row, "retry_exhausted", status="failed", lease_token="", lease_until=0
                )
                return None
            if row["status"] == "pause_requested":
                self._update(conn, row, "paused", status="paused", lease_token="", lease_until=0)
                return None
            return self._update(
                conn,
                row,
                "claimed",
                status="running",
                lease_token=uuid4().hex,
                lease_until=now + lease_seconds,
                attempts=row["attempts"] + 1,
            )

    def fence(self, conn, task_id, token):
        row = (
            conn.execute(select(tasks).where(tasks.c.id == task_id).with_for_update())
            .mappings()
            .one()
        )
        if (
            row["lease_token"] != token
            or row["lease_until"] <= time()
            or row["status"] not in {"running", "pause_requested"}
        ):
            raise Conflict("report lease lost")
        return row

    def finish_step(self, task_id, token, status, state, *, error=False):
        with self.engine.begin() as conn:
            row = self.fence(conn, task_id, token)
            if row["status"] == "pause_requested":
                status = "paused"
            return self._update(
                conn,
                row,
                "step_failed" if error else "checkpointed",
                status=status,
                state_json=state,
                lease_token="",
                lease_until=0,
                attempts=row["attempts"] if error else 0,
                due_at=time() + 5 if error else 0,
            )


class LeasedSaver(ReportCheckpointSaver):
    """Fence every checkpoint/pending-write in the same DB transaction as its write."""

    def __init__(self, store, task_id, token):
        super().__init__(store.engine)
        self.store, self.task_id, self.token = store, task_id, token

    def _save(self, conn, table, values, *, replace=True):
        self.store.fence(conn, self.task_id, self.token)
        return super()._save(conn, table, values, replace=replace)
