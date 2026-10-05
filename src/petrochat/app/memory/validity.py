"""UTC validity shared by retrieval and derived indexes."""
from datetime import datetime, timezone
from typing import Any

UNSET = object()


def normalize_expiry(value: str | datetime | None) -> str | None:
    """Legacy naive database timestamps are UTC; API offsets are normalized."""
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("expires_at must be an ISO datetime or null") from exc


def is_effective(item: Any, now: datetime | None = None) -> bool:
    if item.status != "active":
        return False
    try:
        expiry = normalize_expiry(item.expires_at)
        return expiry is None or expiry > normalize_expiry(now or datetime.now(timezone.utc))
    except ValueError:
        return False  # malformed legacy timestamps fail closed
