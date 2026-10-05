"""Report ownership is derived exclusively from the authenticated user."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from ..core.config import get_settings
from ..report.contracts import ReportRequest
from ..report.store import Conflict, ReportStore
from ..report.workflow import ArtifactStore
from ..sql.engine import get_app_engine
from .auth import CurrentUserDep

router = APIRouter(prefix="/api/reports", tags=["reports"])


def report_store():
    if not get_settings().report_enabled:
        raise HTTPException(503, "报表工作流未启用，请配置 REPORT_ENABLED=true 后重启后端")
    return ReportStore(get_app_engine())


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    action: Literal["approve", "revise", "pause", "resume", "cancel"]
    comment: str = Field(default="", max_length=2000)


def public(row):
    return {
        key: row[key]
        for key in (
            "id",
            "workflow_version",
            "status",
            "revision",
            "question",
            "state_json",
            "created_at",
            "updated_at",
        )
    }


def owned(store, task_id, user):
    try:
        return store.get(task_id, user.user_id)
    except KeyError as exc:
        raise HTTPException(404, "报表不存在") from exc


@router.post("", status_code=201)
def create_report(req: ReportRequest, user: CurrentUserDep, store=Depends(report_store)):
    return public(store.create(user.user_id, req.question))


@router.get("")
def list_reports(user: CurrentUserDep, store=Depends(report_store)):
    return [public(row) for row in store.list(user.user_id)]


@router.get("/{task_id}")
def get_report(task_id: str, user: CurrentUserDep, store=Depends(report_store)):
    return public(owned(store, task_id, user))


@router.post("/{task_id}/actions")
def act(task_id: str, req: ActionRequest, user: CurrentUserDep, store=Depends(report_store)):
    try:
        return public(
            store.action(task_id, user.user_id, req.expected_revision, req.action, req.comment)
        )
    except KeyError as exc:
        raise HTTPException(404, "报表不存在") from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{task_id}/events")
def history(
    task_id: str,
    user: CurrentUserDep,
    after: int = Query(default=0, ge=0),
    store=Depends(report_store),
):
    owned(store, task_id, user)
    return store.history(task_id, user.user_id, after)


@router.get("/{task_id}/artifacts/{kind}")
def download(
    task_id: str,
    kind: Literal["draft", "export", "chart"],
    user: CurrentUserDep,
    store=Depends(report_store),
):
    row = owned(store, task_id, user)
    identity = row["state_json"].get("artifacts", {}).get(kind)
    if not identity or (kind == "export" and row["status"] != "completed"):
        raise HTTPException(404, "当前版本产物尚未就绪")
    try:
        data = ArtifactStore(store, get_settings().report_artifact_dir, row, "").read(identity)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "产物不可用或完整性校验失败，请检查持久卷") from exc
    media, name = {
        "draft": ("text/markdown", "report.md"),
        "export": ("application/zip", "report.zip"),
        "chart": ("image/png", "chart.png"),
    }[kind]
    return Response(
        data,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
