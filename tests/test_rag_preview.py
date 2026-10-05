from datetime import date
from types import SimpleNamespace

from langchain_core.documents import Document
from test_api import auth_headers, client

from petrochat.app.rag import catalog, vector_store
from petrochat.app.rag.evidence import evidence_id


def test_preview_requires_login():
    assert client.get("/api/rag/evidence/E-0123456789abcdef").status_code == 401


def test_preview_rechecks_identity_and_date(monkeypatch):
    doc = Document(page_content="测试原文", metadata={"chunk_id": "c", "snapshot_id": "s"})
    seen = []

    def get():
        scope = catalog._scope.get()
        seen.append((scope["user_id"], scope["as_of"]))
        return [SimpleNamespace(content=doc.page_content, chunk_id="c", metadata=doc.metadata)]

    monkeypatch.setattr(vector_store, "get_chunks", get)
    response = client.get(
        f"/api/rag/evidence/{evidence_id(doc)}?rag_as_of=2024-01-01", headers=auth_headers("2")
    )
    assert response.status_code == 200 and response.json()["content"] == "测试原文"
    assert seen == [("2", date(2024, 1, 1))]


def test_preview_does_not_leak_policy_failure(monkeypatch):
    def denied():
        raise catalog.PolicyError("private policy details")

    monkeypatch.setattr(vector_store, "get_chunks", denied)
    response = client.get("/api/rag/evidence/E-0123456789abcdef", headers=auth_headers())
    assert response.status_code == 404 and "private" not in response.text


def test_preview_rejects_paths_without_querying(monkeypatch):
    def fail():
        raise AssertionError("should not read")

    monkeypatch.setattr(vector_store, "get_chunks", fail)
    assert client.get("/api/rag/evidence/secret.env", headers=auth_headers()).status_code == 404
