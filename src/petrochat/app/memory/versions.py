"""Versioned preference head + audited before/after snapshots in existing tables.

No new schema. Deterministic head identity and optimistic revision prevent
duplicate heads/lost updates. This is lightweight versioning, not bitemporality.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .long_term import MemoryItem, _json_dumps, _now_db
from .preferences import Preference


class PreferenceConflict(ValueError):
    pass


def preference_id(user_id: str, preference: Preference) -> str:
    key = f"petrochat-preference/v1/{int(user_id)}/{preference.scope}/{preference.key}"
    return str(int(hashlib.sha256(key.encode()).hexdigest()[:15], 16))


def put_preference(store, *, user_id: str, preference: Preference, expected_revision: int,
                   actor_id: str | None = None) -> MemoryItem:
    preference = Preference.model_validate(preference.model_dump())
    identity = preference_id(user_id, preference)
    now = _now_db()
    try:
        with store._lock, store.engine.begin() as conn:
            locking = " FOR UPDATE" if store.engine.dialect.name == "mysql" else ""
            row = conn.execute(text("SELECT * FROM user_memory WHERE id=:id" + locking), {"id": identity}).mappings().first()
            current = store._row_to_item(row) if row else None
            before = asdict(current) if current else None
            revision = int(current.metadata.get("revision", 0)) if current else 0
            if current and (current.user_id != str(int(user_id)) or current.metadata.get("scope") != preference.scope
                            or current.metadata.get("key") != preference.key):
                raise PreferenceConflict("preference identity collision")
            if revision != expected_revision:
                raise PreferenceConflict("preference changed; reload current revision")
            if current and current.status != "active":
                raise PreferenceConflict("inactive preference requires explicit review; automatic revival forbidden")
            metadata = {**preference.model_dump(), "revision": revision + 1, "valid_from": now,
                        "kind": "structured_preference", "user_confirmed": True}
            if current and all(current.metadata.get(k) == v for k, v in preference.model_dump().items()):
                return current
            item = MemoryItem(id=identity, user_id=str(int(user_id)), memory_type="query_filter" if preference.key.startswith("query.") else "preference",
                content=preference.content(), source="explicit_preference", confidence=1.0,
                status="active", metadata=metadata, created_at=current.created_at if current else now,
                updated_at=now)
            if current:
                changed = conn.execute(text("""UPDATE user_memory SET content=:content, metadata_json=:metadata,
                    updated_at=:now, expires_at=NULL WHERE id=:id
                    AND JSON_EXTRACT(metadata_json, '$.revision') = :revision AND status='active'"""),
                    {"content": item.content, "metadata": _json_dumps(metadata), "now": now,
                     "id": identity, "revision": revision})
                if changed.rowcount != 1:
                    raise PreferenceConflict("preference changed concurrently")
                before["metadata"]["valid_to"] = now
            else:
                conn.execute(text("""INSERT INTO user_memory
                    (id,user_id,memory_type,content,source,confidence,status,metadata_json,created_at,updated_at,expires_at)
                    VALUES (:id,:user_id,:memory_type,:content,:source,:confidence,:status,:metadata_json,:created_at,:updated_at,NULL)"""),
                    {**asdict(item), "metadata_json": _json_dumps(metadata)})
            store._insert_event(conn, memory_id=identity, user_id=item.user_id,
                event_type="updated" if current else "created", actor_id=actor_id,
                reason="explicit preference revision", payload={"before": before, "after": asdict(item)})
    except IntegrityError as exc:
        raise PreferenceConflict("preference created concurrently; reload current revision") from exc
    store._sync_mem0_updated(item)
    return item
