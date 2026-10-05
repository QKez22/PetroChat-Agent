"""Rebuild the Mem0 active semantic index from MySQL user_memory.

Mem0 is not the source of truth. The script clears the active collection and
replays active MySQL memories into it. Candidate memories are intentionally not
promoted by this script.
"""

from __future__ import annotations

import argparse

from loguru import logger

from petrochat.app.memory import get_long_term_memory_store
from petrochat.app.memory.mem0_adapter import Mem0MemoryAdapter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild Mem0 active index from MySQL user_memory.")
    parser.add_argument("--limit", type=int, default=100_000, help="Maximum active memories to replay.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned work without clearing or syncing.")
    parser.add_argument(
        "--clear-candidates",
        action="store_true",
        help="Also clear the isolated Mem0 candidate collection.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = get_long_term_memory_store()
    memories = store.list_active_memories_for_index(limit=args.limit)
    logger.info("Loaded {} active MySQL memories for Mem0 active-index rebuild.", len(memories))

    if args.dry_run:
        for item in memories[:20]:
            logger.info("Would sync memory_id={} user_id={} type={}", item.id, item.user_id, item.memory_type)
        return

    if args.clear_candidates:
        raise SystemExit("Candidate clearing is no longer part of index repair; use a separately reviewed retention operation.")
    from petrochat.app.core import get_settings
    from petrochat.app.memory.sync import MemorySyncWorker
    if not get_settings().memory_sync_enabled or not get_settings().mem0_enabled:
        raise SystemExit("Run migration 005 and enable MEMORY_SYNC_ENABLED / MEM0_ENABLED first.")
    # Full paginated repair instead of reset + a possibly truncated replay.
    worker = MemorySyncWorker(store, Mem0MemoryAdapter(enabled=True))
    plan = worker.reconcile()
    result = worker.run_once(limit=min(args.limit, 1000))
    logger.info("Repair enqueued: {}; this batch: {}. Drain remaining jobs with sync_memory_index.py --watch", plan, result)
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
