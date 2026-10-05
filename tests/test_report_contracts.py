import pandas as pd
import pytest
from pydantic import ValidationError

from petrochat.app.report import render_report
from petrochat.app.report.contracts import (
    ReportDecision,
    ReportRequest,
    ReportStatus,
    validate_transition,
)


def test_existing_report_baseline_is_deterministic_and_not_truncated_as_total():
    data = pd.DataFrame({"department": ["A", "B", "C"], "tasks": [10, 5, 3]})
    first = render_report(data, title="任务执行概览", with_chart=False, max_rows=2)
    second = render_report(data, title="任务执行概览", with_chart=False, max_rows=2)
    assert first.to_artifact() == second.to_artifact()
    assert first.row_count == 3 and "10" in first.markdown and "后续 1 行省略" in first.markdown
    assert list(data["tasks"]) == [10, 5, 3]


def test_pause_requires_safe_boundary_and_terminal_states_do_not_resume():
    validate_transition(ReportStatus.RUNNING, ReportStatus.PAUSE_REQUESTED)
    validate_transition(ReportStatus.PAUSE_REQUESTED, ReportStatus.PAUSED)
    validate_transition(ReportStatus.PAUSED, ReportStatus.QUEUED)
    with pytest.raises(ValueError):
        validate_transition(ReportStatus.RUNNING, ReportStatus.PAUSED)
    for state in (ReportStatus.COMPLETED, ReportStatus.CANCELLED):
        with pytest.raises(ValueError):
            validate_transition(state, ReportStatus.QUEUED)


def test_inputs_cannot_supply_identity_or_execution_state():
    assert ReportRequest(question="  本月任务统计  ").question == "本月任务统计"
    for payload in ({"question": "   "}, {"question": "本月任务统计", "user_id": "2"}):
        with pytest.raises(ValidationError):
            ReportRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        ReportDecision(action="approve", expected_revision=-1)
