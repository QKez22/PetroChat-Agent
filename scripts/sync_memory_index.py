"""Run a standalone memory worker. Requires migration 005 and both enable flags."""
import argparse
import json
import time

from petrochat.app.core import get_settings
from petrochat.app.memory.long_term import get_long_term_memory_store
from petrochat.app.memory.mem0_adapter import get_mem0_memory_adapter
from petrochat.app.memory.sync import MemorySyncWorker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.memory_sync_enabled or not settings.mem0_enabled:
        raise SystemExit("Enable MEMORY_SYNC_ENABLED and MEM0_ENABLED after migration 005")
    worker = MemorySyncWorker(get_long_term_memory_store(), get_mem0_memory_adapter())
    next_reconcile = 0.0
    while True:
        try:
            if time.monotonic() >= next_reconcile:
                print(json.dumps({"reconcile": worker.reconcile(dry_run=args.dry_run)}), flush=True)
                next_reconcile = time.monotonic() + 300
            if args.dry_run:
                return
            result = worker.run_once()
            print(json.dumps({"sync": result}), flush=True)
            if not args.watch:
                if result["failed"]:
                    raise SystemExit(1)
                return
        except Exception as exc:
            print(json.dumps({"worker_error": type(exc).__name__}), flush=True)
            if not args.watch:
                raise SystemExit(1) from None
        time.sleep(5)


if __name__ == "__main__":
    main()
