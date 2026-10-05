"""请求级执行预算: 在线程和异步任务间共享计数, 请求之间相互隔离。"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock

from langchain_core.callbacks import BaseCallbackHandler


class BudgetExceeded(RuntimeError):
    """在发起下一次外部调用前终止执行。"""


model_run_id: ContextVar[str] = ContextVar("petrochat_model_run", default="")


@dataclass
class RunBudget:
    model_limit: int
    tool_limit: int
    repeat_limit: int
    timeout: float
    started: float = field(default_factory=time.monotonic)
    model_calls: int = 0
    tool_calls: int = 0
    cancelled: bool = False
    reason: str = ""
    model_stats: dict[str, dict] = field(default_factory=dict)
    report_cache: dict[str, dict] = field(default_factory=dict)
    repeats: dict[str, int] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def check(self) -> None:
        if self.cancelled:
            raise BudgetExceeded(self.reason or "本次执行已取消")
        if time.monotonic() - self.started >= self.timeout:
            self.stop("本次任务执行超时")
            raise BudgetExceeded(self.reason)

    def stop(self, reason: str) -> None:
        self.reason = reason
        self.cancelled = True

    def reserve(self, kind: str, signature: str = "") -> None:
        with self.lock:
            self.check()
            if kind == "model":
                if self.model_calls >= self.model_limit:
                    self.stop("已达到模型调用次数上限")
                    raise BudgetExceeded(self.reason)
                self.model_calls += 1
            else:
                if self.tool_calls >= self.tool_limit:
                    self.stop("已达到工具调用次数上限")
                    raise BudgetExceeded(self.reason)
                if self.repeats.get(signature, 0) >= self.repeat_limit:
                    self.stop("相同工具和参数重复调用已达到上限")
                    raise BudgetExceeded(self.reason)
                self.tool_calls += 1
                self.repeats[signature] = self.repeats.get(signature, 0) + 1

    def usage(self) -> dict[str, int]:
        return {"model_calls": self.model_calls, "tool_calls": self.tool_calls}

    def update_model_stats(self, run_id: str, values: dict) -> None:
        with self.lock:
            self.model_stats.setdefault(run_id, {}).update(values)

    def telemetry(self) -> list[dict]:
        with self.lock:
            return [
                {"run_id": key, **{k: v for k, v in row.items() if k != "started"}}
                for key, row in self.model_stats.items()
            ]


_CURRENT: ContextVar[RunBudget | None] = ContextVar("petrochat_run_budget", default=None)


@contextmanager
def budget_scope(budget: RunBudget):
    token = _CURRENT.set(budget)
    try:
        yield budget
    finally:
        budget.stop(budget.reason or "本次执行已结束")
        _CURRENT.reset(token)


def current_budget() -> RunBudget | None:
    return _CURRENT.get()


def reserve_tool(call: dict) -> None:
    if budget := current_budget():
        signature = json.dumps(
            [call["name"], call.get("args", {})], sort_keys=True, ensure_ascii=False
        )
        budget.reserve("tool", signature)


class BudgetCallback(BaseCallbackHandler):
    # 必须抛出预算异常且在当前上下文运行, 不能仅记录 callback 错误后继续调用。
    raise_error = True
    run_inline = True

    def on_chat_model_start(self, serialized, messages, **kwargs):
        if budget := current_budget():
            budget.reserve("model")
            run_id = str(kwargs.get("run_id", ""))
            model_run_id.set(run_id)
            budget.update_model_stats(
                run_id,
                {
                    "node": (kwargs.get("metadata") or {}).get("langgraph_node", "model"),
                    "started": time.monotonic(),
                    "outcome": "running",
                },
            )

    def on_llm_end(self, response, **kwargs):
        if budget := current_budget():
            run_id = str(kwargs.get("run_id", ""))
            started = budget.model_stats.get(run_id, {}).get("started", time.monotonic())
            usage = None
            for generations in response.generations:
                for generation in generations:
                    usage = (
                        getattr(getattr(generation, "message", None), "usage_metadata", None)
                        or usage
                    )
            budget.update_model_stats(
                run_id,
                {
                    "outcome": "completed",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "actual_usage": usage,
                },
            )

    def on_llm_error(self, error, **kwargs):
        if budget := current_budget():
            run_id = str(kwargs.get("run_id", ""))
            started = budget.model_stats.get(run_id, {}).get("started", time.monotonic())
            budget.update_model_stats(
                run_id,
                {"outcome": "failed", "latency_ms": int((time.monotonic() - started) * 1000)},
            )
