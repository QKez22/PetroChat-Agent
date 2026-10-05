"""Ensure the supplemental permission repair cannot grant business/global writes."""
import re
from pathlib import Path


def test_memory_grants_are_limited_to_two_legacy_application_tables():
    sql = (Path(__file__).resolve().parents[1] / "scripts/migrations/006_memory_governance_grants.sql").read_text(encoding="utf-8")
    statements = [line.strip() for line in sql.splitlines() if line.strip() and not line.startswith("--")]
    assert statements[0] == "USE timing_task;"
    expected = {
        "GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.user_memory TO 'petrochat_app'@'%';",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON timing_task.memory_event TO 'petrochat_app'@'%';",
    }
    assert set(statements[1:]) == expected
    assert len(statements) == 3
    assert not re.search(r"ALL PRIVILEGES|WITH GRANT OPTION|ON\s+\*", "\n".join(statements), re.I)
