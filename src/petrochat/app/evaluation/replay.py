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
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage

from petrochat.app.agent import build_graph, build_initial_state

Mode = Literal["oracle", "agent"]

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


def _oracle_predictions(golden_dir: Path, limit: int | None = None) -> list[dict[str, Any]]:
    turns = _read_csv(golden_dir / "golden_dialogue_turns.csv")
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


async def _agent_predictions(golden_dir: Path, limit: int | None = None) -> list[dict[str, Any]]:
    turns = _read_csv(golden_dir / "golden_dialogue_turns.csv")
    grouped = _turn_groups(turns)
    graph = build_graph()
    rows: list[dict[str, Any]] = []

    for dialogue_id, dialogue_turns in grouped.items():
        history: list[dict[str, str]] = []
        for turn in dialogue_turns:
            if limit is not None and len(rows) >= limit:
                return rows
            question = turn.get("user_message", "")
            started_at = time.perf_counter()
            try:
                state = await graph.ainvoke(build_initial_state(
                    question,
                    session_id=f"eval-{dialogue_id}",
                    user_id=turn.get("user_role") or "engineer",
                    history=history,
                ))
                answer = _latest_answer(state)
                status = "ok"
                error = ""
                route = state.get("next") or "general"
                retrieved = _retrieved_payload(state)
                sql = _extract_sql(answer)
            except Exception as exc:  # pragma: no cover - depends on online services
                answer = ""
                status = "error"
                error = str(exc)
                route = "error"
                retrieved = []
                sql = ""

            latency_ms = int((time.perf_counter() - started_at) * 1000)
            rows.append({
                "dialogue_id": dialogue_id,
                "turn_id": turn["turn_id"],
                "mode": "agent",
                "user_role": turn.get("user_role"),
                "scenario_type": turn.get("scenario_type"),
                "question": question,
                "route": route,
                "answer": answer,
                "sql": sql,
                "retrieved": retrieved,
                "status": status,
                "error": error,
                "latency_ms": latency_ms,
            })
            history.append({"role": "user", "content": question})
            if answer:
                history.append({"role": "assistant", "content": answer})

    return rows


async def generate_predictions_async(
    golden_dir: Path,
    output_path: Path,
    *,
    mode: Mode = "oracle",
    limit: int | None = None,
) -> dict[str, Any]:
    if mode == "oracle":
        rows = _oracle_predictions(golden_dir, limit=limit)
    elif mode == "agent":
        rows = await _agent_predictions(golden_dir, limit=limit)
    else:
        raise ValueError(f"unsupported replay mode: {mode}")

    count = _write_jsonl(output_path, rows)
    return {
        "mode": mode,
        "golden_dir": str(golden_dir),
        "output_path": str(output_path),
        "prediction_count": count,
    }


def generate_predictions(
    golden_dir: Path,
    output_path: Path,
    *,
    mode: Mode = "oracle",
    limit: int | None = None,
) -> dict[str, Any]:
    return asyncio.run(generate_predictions_async(
        golden_dir=golden_dir,
        output_path=output_path,
        mode=mode,
        limit=limit,
    ))
