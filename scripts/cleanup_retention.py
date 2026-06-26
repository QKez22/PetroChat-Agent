"""Run data retention cleanup for PetroChat application tables.

Default mode is dry-run. Add --execute to mutate data.
"""

from __future__ import annotations

import argparse
import json
import warnings

warnings.simplefilter("ignore")

from petrochat.app.core.config import get_settings  # noqa: E402
from petrochat.app.retention import RetentionCleanupService, RetentionConfig  # noqa: E402


def _config_from_settings() -> RetentionConfig:
    settings = get_settings()
    return RetentionConfig(
        conversation_days=settings.retention_conversation_days,
        conversation_recovery_days=settings.retention_conversation_recovery_days,
        tool_log_days=settings.retention_tool_log_days,
        retrieval_context_days=settings.retention_retrieval_context_days,
        audit_log_days=settings.retention_audit_log_days,
        temp_file_days=settings.retention_temp_file_days,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PetroChat retention cleanup")
    parser.add_argument("--execute", action="store_true", help="Actually mutate/delete data")
    parser.add_argument("--actor-id", default="", help="Operator user_id written to audit log")
    parser.add_argument("--reason", default="manual retention cleanup", help="Cleanup reason")
    parser.add_argument("--conversation-days", type=int, default=None)
    parser.add_argument("--conversation-recovery-days", type=int, default=None)
    parser.add_argument("--tool-log-days", type=int, default=None)
    parser.add_argument("--retrieval-context-days", type=int, default=None)
    parser.add_argument("--audit-log-days", type=int, default=None)
    args = parser.parse_args()

    config = _config_from_settings()
    overrides = {
        "conversation_days": args.conversation_days,
        "conversation_recovery_days": args.conversation_recovery_days,
        "tool_log_days": args.tool_log_days,
        "retrieval_context_days": args.retrieval_context_days,
        "audit_log_days": args.audit_log_days,
    }
    config = RetentionConfig(**{
        **config.__dict__,
        **{key: value for key, value in overrides.items() if value is not None},
    })

    result = RetentionCleanupService().run(
        dry_run=not args.execute,
        config=config,
        actor_id=args.actor_id or None,
        reason=args.reason,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
