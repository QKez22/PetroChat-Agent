"""Report-only synchronous LangGraph saver for a serial background worker.

Full checkpoint + pending writes, not a progress JSON. No automatic DDL, pickle,
pruning, cross-version migration or public unrestricted checkpoint API.
"""

from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_metadata,
)
from sqlalchemy import Column, Integer, LargeBinary, MetaData, String, Table, and_, delete, select
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

schema = MetaData()
blob = LargeBinary().with_variant(LONGBLOB(), "mysql")
checkpoints = Table(
    "agent_report_checkpoint",
    schema,
    Column("thread_id", String(64), primary_key=True),
    Column("namespace", String(255), primary_key=True),
    Column("checkpoint_id", String(64), primary_key=True),
    Column("parent_id", String(64)),
    Column("data_type", String(32), nullable=False),
    Column("data", blob, nullable=False),
    Column("meta_type", String(32), nullable=False),
    Column("metadata", blob, nullable=False),
)
writes_table = Table(
    "agent_report_write",
    schema,
    Column("thread_id", String(64), primary_key=True),
    Column("namespace", String(255), primary_key=True),
    Column("checkpoint_id", String(64), primary_key=True),
    Column("task_id", String(64), primary_key=True),
    Column("write_index", Integer, primary_key=True),
    Column("channel", String(255), nullable=False),
    Column("task_path", String(1024), nullable=False),
    Column("data_type", String(32), nullable=False),
    Column("data", blob, nullable=False),
)


class ReportCheckpointSaver(BaseCheckpointSaver):
    """v1 supports sync StateGraph, ordinary channels, one leased writer/thread.

    API handlers must authorize the report owner before constructing thread_id.
    No claim of general-purpose saver compatibility beyond tested report graphs.
    """

    def __init__(self, engine: Engine):
        super().__init__()
        if engine.dialect.name not in {"mysql", "sqlite"}:
            raise ValueError("unsupported report checkpoint database")
        self.engine = engine

    def _key(self, config: RunnableConfig) -> dict[str, str]:
        values = config["configurable"]
        thread, namespace = str(values["thread_id"]), values.get("checkpoint_ns", "")
        if not thread or len(thread) > 64 or len(namespace) > 255:
            raise ValueError("invalid report checkpoint identity")
        return {"thread_id": thread, "namespace": namespace}

    @staticmethod
    def _where(table, key):
        return and_(*(table.c[k] == value for k, value in key.items()))

    def _save(self, conn, table, values: dict, *, replace: bool = True):
        key_columns = [c.name for c in table.primary_key]
        insert = mysql_insert if self.engine.dialect.name == "mysql" else sqlite_insert
        stmt = insert(table).values(**values)
        if self.engine.dialect.name == "mysql":
            changes = (
                {k: stmt.inserted[k] for k in values if k not in key_columns}
                if replace
                else {key_columns[0]: table.c[key_columns[0]]}
            )
            stmt = stmt.on_duplicate_key_update(**changes)
        elif replace:
            stmt = stmt.on_conflict_do_update(
                index_elements=key_columns,
                set_={k: stmt.excluded[k] for k in values if k not in key_columns},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=key_columns)
        conn.execute(stmt)

    def _encode(self, value):
        kind, data = self.serde.dumps_typed(value)
        if kind == "pickle" or len(data) > 4 * 1024 * 1024:
            raise ValueError("checkpoint must be small and pickle-free; store artifact references")
        return kind, data

    def _decode(self, kind, data):
        if kind not in {"json", "msgpack", "bytes", "bytearray", "null"}:
            raise ValueError("unsupported checkpoint serialization")
        return self.serde.loads_typed((kind, data))

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> RunnableConfig:
        key = {**self._key(config), "checkpoint_id": checkpoint["id"]}
        kind, data = self._encode(checkpoint)
        meta_kind, meta = self._encode(get_checkpoint_metadata(config, metadata))
        with self.engine.begin() as conn:
            self._save(
                conn,
                checkpoints,
                {
                    **key,
                    "parent_id": config["configurable"].get("checkpoint_id"),
                    "data_type": kind,
                    "data": data,
                    "meta_type": meta_kind,
                    "metadata": meta,
                },
            )
        return self._config(key)

    @staticmethod
    def _config(key):
        return {
            "configurable": {
                "thread_id": key["thread_id"],
                "checkpoint_ns": key["namespace"],
                "checkpoint_id": key["checkpoint_id"],
            }
        }

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        key = self._key(config)
        if config["configurable"].get("checkpoint_id"):
            key["checkpoint_id"] = config["configurable"]["checkpoint_id"]
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(checkpoints)
                    .where(self._where(checkpoints, key))
                    .order_by(checkpoints.c.checkpoint_id.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            pending = (
                conn.execute(
                    select(writes_table)
                    .where(
                        self._where(
                            writes_table,
                            {k: row[k] for k in ("thread_id", "namespace", "checkpoint_id")},
                        )
                    )
                    .order_by(
                        writes_table.c.task_path, writes_table.c.task_id, writes_table.c.write_index
                    )
                )
                .mappings()
                .all()
            )
        parent = {**row, "checkpoint_id": row["parent_id"]}
        return CheckpointTuple(
            config=self._config(row),
            checkpoint=self._decode(row["data_type"], row["data"]),
            metadata=self._decode(row["meta_type"], row["metadata"]),
            parent_config=self._config(parent) if row["parent_id"] else None,
            pending_writes=[
                (r["task_id"], r["channel"], self._decode(r["data_type"], r["data"]))
                for r in pending
            ],
        )

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        key = {
            **self._key(config),
            "checkpoint_id": config["configurable"]["checkpoint_id"],
            "task_id": task_id,
        }
        with self.engine.begin() as conn:
            for index, (channel, value) in enumerate(writes):
                kind, data = self._encode(value)
                slot = WRITES_IDX_MAP.get(channel, index)
                self._save(
                    conn,
                    writes_table,
                    {
                        **key,
                        "write_index": slot,
                        "channel": channel,
                        "task_path": task_path,
                        "data_type": kind,
                        "data": data,
                    },
                    replace=slot < 0,
                )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        # Deliberately refuse global enumeration; report API is owner-scoped.
        if config is None:
            raise ValueError("report thread config required")
        key = self._key(config)
        if config["configurable"].get("checkpoint_id"):
            key["checkpoint_id"] = config["configurable"]["checkpoint_id"]
        query = select(checkpoints).where(self._where(checkpoints, key))
        if before:
            query = query.where(
                checkpoints.c.checkpoint_id < before["configurable"]["checkpoint_id"]
            )
        with self.engine.connect() as conn:
            rows = conn.execute(query.order_by(checkpoints.c.checkpoint_id.desc())).mappings().all()
        yielded = 0
        for row in rows:
            if limit is not None and yielded >= limit:
                break
            metadata = self._decode(row["meta_type"], row["metadata"])
            if filter and any(metadata.get(k) != v for k, v in filter.items()):
                continue
            item = self.get_tuple(self._config(row))
            if item is not None:
                yielded += 1
                yield item

    def delete_thread(self, thread_id: str) -> None:
        self._key({"configurable": {"thread_id": thread_id}})
        with self.engine.begin() as conn:
            conn.execute(delete(writes_table).where(writes_table.c.thread_id == thread_id))
            conn.execute(delete(checkpoints).where(checkpoints.c.thread_id == thread_id))
