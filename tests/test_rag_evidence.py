from datetime import date

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from petrochat.app.agent.nodes.qa_node import qa_node
from petrochat.app.agent.result import build_turn_result
from petrochat.app.rag.catalog import PolicyError
from petrochat.app.rag.evidence import (
    Draft,
    build_evidence_graph,
    evidence_id,
    render_result,
    validate_quotes,
)


def source():
    return Document(
        page_content="测试夹具：压力不得超过 2 MPa，特殊设备除外。",
        metadata={"chunk_id": "fixture", "source_doc": "测试夹具", "snapshot_id": "s"},
    )


def draft(doc, **kwargs):
    return Draft(
        status="answered",
        claims=[
            {
                "text": kwargs.get("text", "压力不得超过 2 MPa，特殊设备除外。"),
                "evidence": [
                    {
                        "evidence_id": kwargs.get("id", evidence_id(doc)),
                        "quote": kwargs.get("quote", doc.page_content),
                    }
                ],
            }
        ],
    )


def test_unknown_id_and_fabricated_quotes_rejected():
    doc = source()
    assert validate_quotes(draft(doc), [doc])
    assert not validate_quotes(draft(doc, id="fake"), [doc])
    assert not validate_quotes(draft(doc, quote="压力可超过2 MPa"), [doc])
    assert not validate_quotes(draft(doc, text="压力为 20 MPa"), [doc])
    assert not validate_quotes(draft(doc, text="压力要求 [E-fake]"), [doc])


def test_one_retry_then_stop_no_unverified_text():
    doc, calls = source(), []
    graph = build_evidence_graph(
        lambda q: calls.append(q) or [doc],
        lambda q, ds: draft(doc, quote="虚构内容"),
        lambda *a: True,
    )
    state = graph.invoke({"question": "压力要求？"})
    assert len(calls) == 2 and not state["valid"]
    result = render_result(state)
    assert result["rag_status"] == "insufficient" and result["evidence"] == []
    assert "虚构内容" not in result["answer"]


def test_semantic_failure_cannot_pass_with_real_quote():
    doc = source()
    state = build_evidence_graph(
        lambda q: [doc], lambda q, ds: draft(doc, text="压力可以超过 2 MPa"), lambda *a: False
    ).invoke({"question": "q"})
    assert state["attempts"] == 2 and render_result(state)["citations"] == []


def test_success_one_pass_and_version_warning():
    doc = source()
    state = build_evidence_graph(lambda q: [doc], lambda q, ds: draft(doc), lambda *a: True).invoke(
        {"question": "q"}
    )
    result = render_result(state)
    assert state["attempts"] == 1
    assert result["evidence"][0]["content"] == doc.page_content
    assert "生效日期尚未核实" in result["answer"]
    turn = build_turn_result({**result, "messages": [AIMessage(content=result["answer"])]})
    assert turn.citations == [evidence_id(doc)]


def test_policy_failure_is_not_retried():
    calls = []

    def fail(q):
        calls.append(q)
        raise PolicyError("版本需核查")

    state = build_evidence_graph(fail).invoke({"question": "q"})
    assert len(calls) == 1 and state["status"] == "needs_review"


def test_missing_historical_date_does_not_retrieve():
    assert qa_node({"question": "去年规范要求是什么？"})["rag_status"] == "needs_clarification"


def test_legacy_cannot_claim_historical_validity(monkeypatch):
    from petrochat.app.core import get_settings

    monkeypatch.setattr(get_settings(), "rag_catalog_enabled", False)
    assert qa_node({"question": "q", "rag_as_of": date(2020, 1, 1)})["rag_status"] == "needs_review"
