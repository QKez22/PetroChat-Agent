"""Golden Set replay utilities.

Two modes are supported:
- oracle: copy expected contracts into prediction JSONL, useful for pipeline checks;
- agent: invoke the current LangGraph agent turn by turn, useful for real regression runs.
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage

from petrochat.app.agent import build_graph, build_initial_state

Mode = Literal["oracle", "agent"]
AgentRunner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

SQL_BLOCK_PATTERN = re.compile(r"```sql\s*(.*?)```", re.I | re.S)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _loads_json(value: str, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _index_by_key(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["dialogue_id"], row["turn_id"]): row for row in rows}


def _latest_answer(state: dict[str, Any]) -> str:
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def _extract_sql(answer: str) -> str:
    match = SQL_BLOCK_PATTERN.search(answer or "")
    return match.group(1).strip() if match else ""


def _retrieved_payload(state: dict[str, Any]) -> list[dict[str, Any]]:
    retrieved = state.get("retrieved") or []
    payload = []
    for item in retrieved:
        metadata = item.get("metadata") or {}
        payload.append({
            "chunk_id": item.get("chunk_id"),
            "source_doc": metadata.get("source_doc"),
            "section_number": metadata.get("section_number"),
            "score": item.get("score"),
        })
    return payload


def _turn_groups(turns: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in turns:
        grouped[row["dialogue_id"]].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda item: int(item["turn_id"]))
    return dict(sorted(grouped.items()))


def _filter_turns(
    turns: list[dict[str, str]],
    *,
    scenario_type: str | None = None,
    dialogue_ids: set[str] | None = None,
) -> list[dict[str, str]]:
    filtered = turns
    if scenario_type:
        filtered = [row for row in filtered if row.get("scenario_type") == scenario_type]
    if dialogue_ids:
        filtered = [row for row in filtered if row.get("dialogue_id") in dialogue_ids]
    return filtered


def _oracle_predictions(
    golden_dir: Path,
    limit: int | None = None,
    *,
    scenario_type: str | None = None,
    dialogue_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    turns = _filter_turns(
        _read_csv(golden_dir / "golden_dialogue_turns.csv"),
        scenario_type=scenario_type,
        dialogue_ids=dialogue_ids,
    )
    sql_by_key = _index_by_key(_read_csv(golden_dir / "golden_sql_expectation.csv"))
    rag_by_key = _index_by_key(_read_csv(golden_dir / "golden_rag_evidence.csv"))
    memory_by_key = _index_by_key(_read_csv(golden_dir / "golden_memory_state.csv"))

    rows: list[dict[str, Any]] = []
    for turn in turns:
        if limit is not None and len(rows) >= limit:
            break
        key = (turn["dialogue_id"], turn["turn_id"])
        sql_row = sql_by_key.get(key)
        rag_row = rag_by_key.get(key)
        memory_row = memory_by_key.get(key)
        rows.append({
            "dialogue_id": turn["dialogue_id"],
            "turn_id": turn["turn_id"],
            "mode": "oracle",
            "user_role": turn.get("user_role"),
            "scenario_type": turn.get("scenario_type"),
            "question": turn.get("user_message"),
            "route": "sql" if sql_row else "qa" if rag_row else "general",
            "answer": "; ".join(_loads_json(turn.get("expected_answer_points", ""), [])),
            "sql": sql_row.get("expected_sql_template", "") if sql_row else "",
            "retrieved": [
                {
                    "source_doc": rag_row.get("expected_source_file"),
                    "section_number": rag_row.get("expected_section"),
                    "chunk_id": rag_row.get("expected_chunk_id"),
                }
            ] if rag_row else [],
            "memory_after": _loads_json(memory_row.get("memory_after", ""), {}) if memory_row else {},
            "status": "ok",
            "latency_ms": 0,
        })
    return rows


async def _default_agent_runner(state: dict[str, Any]) -> dict[str, Any]:
    graph = build_graph()
    return await graph.ainvoke(state)


async def _agent_predictions(
    golden_dir: Path,
    limit: int | None = None,
    *,
    scenario_type: str | None = None,
    dialogue_ids: set[str] | None = None,
    eval_user_id: str = "0",
    run_id: str = "",
    runner: AgentRunner | None = None,
) -> list[dict[str, Any]]:
    turns = _filter_turns(
        _read_csv(golden_dir / "golden_dialogue_turns.csv"),
        scenario_type=scenario_type,
        dialogue_ids=dialogue_ids,
    )
    grouped = _turn_groups(turns)
    runner = runner or _default_agent_runner
    rows: list[dict[str, Any]] = []

    for dialogue_id, dialogue_turns in grouped.items():
        history: list[dict[str, str]] = []
        for turn in dialogue_turns:
            if limit is not None and len(rows) >= limit:
                return rows
            question = turn.get("user_message", "")
            session_id = f"eval-{run_id}-{dialogue_id}" if run_id else f"eval-{dialogue_id}"
            started_at = time.perf_counter()
            try:
                initial_state = build_initial_state(
                    question,
                    session_id=session_id,
                    user_id=eval_user_id,
                    history=history,
                )
                state = await runner(initial_state)
                answer = _latest_answer(state)
                status = "ok"
                error = ""
                route = state.get("next") or "general"
                retrieved = _retrieved_payload(state)
                sql = _extract_sql(answer)
                memory_used = [
                    item.get("id")
                    for item in state.get("long_term_memories", [])
                    if isinstance(item, dict) and item.get("id")
                ]
            except Exception as exc:  # pragma: no cover - depends on online services
                answer = ""
                status = "error"
                error = str(exc)
                route = "error"
                retrieved = []
                sql = ""
                memory_used = []

            latency_ms = int((time.perf_counter() - started_at) * 1000)
            rows.append({
                "run_id": run_id,
                "session_id": session_id,
                "dialogue_id": dialogue_id,
                "turn_id": turn["turn_id"],
                "mode": "agent",
                "user_role": turn.get("user_role"),
                "eval_user_id": eval_user_id,
                "scenario_type": turn.get("scenario_type"),
                "question": question,
                "route": route,
                "answer": answer,
                "sql": sql,
                "retrieved": retrieved,
                "memory_used": memory_used,
                "status": status,
                "error": error,
                "latency_ms": latency_ms,
            })
            history.append({"role": "user", "content": question})
            if answer:
                history.append({"role": "assistant", "content": answer})

    return rows


def _prediction_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    ok_count = sum(1 for row in rows if row.get("status") == "ok")
    error_count = count - ok_count
    latencies = [int(row.get("latency_ms") or 0) for row in rows]
    routes: dict[str, int] = {}
    scenarios: dict[str, int] = {}
    for row in rows:
        route = str(row.get("route") or "unknown")
        scenario = str(row.get("scenario_type") or "unknown")
        routes[route] = routes.get(route, 0) + 1
        scenarios[scenario] = scenarios.get(scenario, 0) + 1
    return {
        "prediction_count": count,
        "ok_count": ok_count,
        "error_count": error_count,
        "success_rate": round(ok_count / (count or 1), 4),
        "avg_latency_ms": round(sum(latencies) / (count or 1), 2),
        "max_latency_ms": max(latencies) if latencies else 0,
        "route_counts": routes,
        "scenario_counts": scenarios,
    }


async def generate_predictions_async(
    golden_dir: Path,
    output_path: Path,
    *,
    mode: Mode = "oracle",
    limit: int | None = None,
    scenario_type: str | None = None,
    dialogue_ids: set[str] | None = None,
    eval_user_id: str = "0",
    run_id: str | None = None,
    summary_path: Path | None = None,
    runner: AgentRunner | None = None,
) -> dict[str, Any]:
    run_id = run_id or f"{mode}-{int(time.time())}"
    if mode == "oracle":
        rows = _oracle_predictions(
            golden_dir,
            limit=limit,
            scenario_type=scenario_type,
            dialogue_ids=dialogue_ids,
        )
    elif mode == "agent":
        rows = await _agent_predictions(
            golden_dir,
            limit=limit,
            scenario_type=scenario_type,
            dialogue_ids=dialogue_ids,
            eval_user_id=eval_user_id,
            run_id=run_id,
            runner=runner,
        )
    else:
        raise ValueError(f"unsupported replay mode: {mode}")

    count = _write_jsonl(output_path, rows)
    summary = {
        "run_id": run_id,
        "mode": mode,
        "golden_dir": str(golden_dir),
        "output_path": str(output_path),
        "summary_path": str(summary_path) if summary_path else "",
        "limit": limit,
        "scenario_type": scenario_type or "",
        "dialogue_ids": sorted(dialogue_ids) if dialogue_ids else [],
        "eval_user_id": eval_user_id if mode == "agent" else "",
        "prediction_count": count,
        "prediction_summary": _prediction_summary(rows),
    }
    if summary_path:
        _write_json(summary_path, summary)
    return summary


def generate_predictions(
    golden_dir: Path,
    output_path: Path,
    *,
    mode: Mode = "oracle",
    limit: int | None = None,
    scenario_type: str | None = None,
    dialogue_ids: set[str] | None = None,
    eval_user_id: str = "0",
    run_id: str | None = None,
    summary_path: Path | None = None,
    runner: AgentRunner | None = None,
) -> dict[str, Any]:
    return asyncio.run(generate_predictions_async(
        golden_dir=golden_dir,
        output_path=output_path,
        mode=mode,
        limit=limit,
        scenario_type=scenario_type,
        dialogue_ids=dialogue_ids,
        eval_user_id=eval_user_id,
        run_id=run_id,
        summary_path=summary_path,
        runner=runner,
    ))
