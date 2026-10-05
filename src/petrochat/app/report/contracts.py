"""Durable report v1 contracts, separate from conversational AgentState."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WORKFLOW_VERSION = "report-v1"


class ReportStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


TRANSITIONS: dict[ReportStatus, frozenset[ReportStatus]] = {
    ReportStatus.QUEUED: frozenset(
        {ReportStatus.RUNNING, ReportStatus.PAUSED, ReportStatus.CANCELLED}
    ),
    ReportStatus.RUNNING: frozenset(
        {
            ReportStatus.AWAITING_INPUT,
            ReportStatus.PAUSE_REQUESTED,
            ReportStatus.FAILED,
            ReportStatus.COMPLETED,
            ReportStatus.CANCELLED,
        }
    ),
    ReportStatus.PAUSE_REQUESTED: frozenset(
        {ReportStatus.PAUSED, ReportStatus.FAILED, ReportStatus.CANCELLED}
    ),
    ReportStatus.AWAITING_INPUT: frozenset({ReportStatus.QUEUED, ReportStatus.CANCELLED}),
    ReportStatus.PAUSED: frozenset({ReportStatus.QUEUED, ReportStatus.CANCELLED}),
    ReportStatus.FAILED: frozenset({ReportStatus.QUEUED, ReportStatus.CANCELLED}),
    ReportStatus.COMPLETED: frozenset(),
    ReportStatus.CANCELLED: frozenset(),
}


def validate_transition(current: ReportStatus, target: ReportStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise ValueError(f"invalid report transition: {current} -> {target}")


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=2000)
    output_format: Literal["zip"] = "zip"  # Markdown + CSV + PNG; no email side effects

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("report question is too short")
        return value


class ReportDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    action: Literal["approve", "revise", "cancel"]
    comment: str = Field(default="", max_length=2000)


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str
    kind: Literal["snapshot", "chart", "draft", "export"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
