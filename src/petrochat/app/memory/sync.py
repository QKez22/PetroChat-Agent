"""Transactional coalescing outbox and repeatable repair of a derived index.

At-least-once, not exactly-once. A stale/late vector is rejected on the read path
by its fingerprint and repaired by the periodic full reconciliation.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict

from sqlalchemy import BigInteger, Column, Float, Integer, MetaData, String, Table, select, text, update

from .validity import is_effective

schema = MetaData()
jobs = Table("agent_memory_sync", schema,
    Column("memory_id", BigInteger, primary_key=True),
    Column("user_id", BigInteger, nullable=False),
    Column("generation", Integer, nullable=False),
    Column("pending", Integer, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("due_at", Float, nullable=False),
    Column("lease_until", Float, nullable=False),
    Column("lease_token", String(64), nullable=False),
    Column("last_error", String(120), nullable=False),
)


def fingerprint(item) -> str:
    return hashlib.sha256(json.dumps(asdict(item), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def enqueue(conn, memory_id: str, user_id: str) -> None:
    """Must run in the business transaction; a missing table fails the write."""
    changed = conn.execute(update(jobs).where(jobs.c.memory_id == int(memory_id)).values(
        generation=jobs.c.generation + 1, pending=1, attempts=0, due_at=time.time(), last_error="",
    ))
    if not changed.rowcount:
        conn.execute(jobs.insert().values(memory_id=int(memory_id), user_id=int(user_id),
            generation=1, pending=1, attempts=0, due_at=time.time(), lease_until=0,
            lease_token="", last_error=""))


class MemorySyncWorker:
    def __init__(self, store, adapter, *, clock=time.time, lease_seconds=120):
        self.store, self.adapter, self.clock = store, adapter, clock
        self.lease_seconds = lease_seconds

    def run_once(self, limit: int = 100) -> dict[str, int]:
        if not self.adapter.enabled:
            raise RuntimeError("MEM0_ENABLED is required for the sync worker")
        counts = {"succeeded": 0, "failed": 0, "superseded": 0}
        now = self.clock()
        with self.store.engine.connect() as conn:
            candidates = conn.execute(select(jobs).where(jobs.c.pending == 1,
                jobs.c.due_at <= now, jobs.c.lease_until <= now).order_by(jobs.c.due_at, jobs.c.memory_id)
                .limit(max(1, min(limit, 1000)))).mappings().all()
        for row in candidates:
            token = uuid.uuid4().hex
            with self.store.engine.begin() as conn:
                claimed = conn.execute(update(jobs).where(jobs.c.memory_id == row["memory_id"],
                    jobs.c.generation == row["generation"], jobs.c.pending == 1,
                    jobs.c.lease_until <= self.clock()).values(
                    lease_token=token, lease_until=self.clock() + self.lease_seconds))
            if not claimed.rowcount:
                continue
            error = ""
            try:
                item = self.store.get_memory(str(row["memory_id"]))
                self.adapter.sync_current(item, memory_id=str(row["memory_id"]), user_id=str(row["user_id"]))
            except Exception as exc:
                error = type(exc).__name__  # never persist credentials or raw memory in error strings
            with self.store.engine.begin() as conn:
                current = conn.execute(select(jobs).where(jobs.c.memory_id == row["memory_id"]).with_for_update()).mappings().one()
                if current["lease_token"] != token:
                    counts["superseded"] += 1
                    continue
                newer = current["generation"] != row["generation"]
                attempts = current["attempts"] + 1 if error and not newer else 0
                conn.execute(update(jobs).where(jobs.c.memory_id == row["memory_id"], jobs.c.lease_token == token).values(
                    pending=int(bool(error) or newer), attempts=attempts,
                    due_at=self.clock() + (min(300, 2 ** min(attempts, 8)) if error and not newer else 0),
                    lease_until=0, lease_token="", last_error=error,
                ))
            counts["failed" if error else "superseded" if newer else "succeeded"] += 1
        return counts

    def reconcile(self, page_size: int = 200, *, dry_run: bool = False) -> dict[str, int]:
        """Keyset scan of ALL MySQL rows; never infer absence from a LIMIT slice."""
        counts = {"scanned": 0, "repair": 0, "orphan": 0}
        after = 0
        while True:
            with self.store.engine.connect() as conn:
                rows = conn.execute(text("SELECT * FROM user_memory WHERE id > :after ORDER BY id LIMIT :size"),
                    {"after": after, "size": max(1, min(page_size, 1000))}).mappings().all()
            if not rows:
                break
            for row in rows:
                item = self.store._row_to_item(row)
                indexed = self.adapter.indexed_state(item.user_id, item.id)
                expected = [fingerprint(item)] if is_effective(item) else []
                counts["scanned"] += 1
                if indexed != expected:
                    counts["repair"] += 1
                    if not dry_run:
                        with self.store.engine.begin() as conn:
                            enqueue(conn, item.id, item.user_id)
            after = rows[-1]["id"]
        # Only explicitly owned rows are eligible. No index mutation during pagination.
        for user_id, memory_id in self.adapter.iter_index_keys(page_size=page_size):
            item = self.store.get_memory(memory_id)
            if item is None or item.user_id != user_id:
                counts["orphan"] += 1
                if not dry_run:
                    # Mismatched tenant metadata is removed by repairing that index key,
                    # never by writing the other user's MySQL row.
                    self.adapter.remove_index_key(user_id, memory_id)
        return counts
