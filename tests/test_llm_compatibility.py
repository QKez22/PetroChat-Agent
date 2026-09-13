"""通过本地 HTTP 服务验证升级后的真实 SDK 协议, 不调用付费模型。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from petrochat.app.agent.nodes.supervisor_node import RouteDecision
from petrochat.app.core.llm import get_chat_llm, get_embedding, get_reasoner_llm
from petrochat.app.core.state import AgentState
from petrochat.app.tools import convert_unit


@pytest.fixture
def compatible_api(monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            self.send_response(200)
            if self.path == "/v1/embeddings":
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                payload = {
                    "data": [
                        {"index": i, "embedding": [0.125] * 1024}
                        for i, _ in enumerate(body["input"])
                    ],
                    "model": body["model"],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                }
                self.wfile.write(json.dumps(payload).encode())
                return

            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            delta = {"role": "assistant", "content": ""}
            finish = "stop"
            if body.get("tools"):
                name = body["tools"][0]["function"]["name"]
                args = (
                    {"next": "general", "reasoning": "unit conversion"}
                    if name == "RouteDecision"
                    else {"value": 1, "from_unit": "MPa", "to_unit": "psi"}
                )
                delta["tool_calls"] = [
                    {
                        "index": 0,
                        "id": "call_test",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ]
                finish = "tool_calls"
            else:
                delta["content"] = "compatibility-ok"
            for chunk_delta, reason in [(delta, None), ({}, finish)]:
                chunk = {
                    "id": "test-completion",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": body["model"],
                    "choices": [{"index": 0, "delta": chunk_delta, "finish_reason": reason}],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    for name, value in {
        "DEEPSEEK_BASE_URL": url,
        "DASHSCOPE_BASE_URL": url,
        "DEEPSEEK_API_KEY": "test-key",
        "DASHSCOPE_API_KEY": "test-key",
        "EMBEDDING_DIM": "1024",
        "EMBEDDING_BATCH_SIZE": "2",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    }.items():
        monkeypatch.setenv(name, value)
    from petrochat.app.core import get_settings

    factories = (get_settings, get_chat_llm, get_reasoner_llm, get_embedding)
    for factory in factories:
        factory.cache_clear()
    try:
        yield requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        for factory in factories:
            factory.cache_clear()


def test_streaming_structured_output_uses_function_calling(compatible_api):
    result = (
        get_chat_llm()
        .with_structured_output(RouteDecision, method="function_calling")
        .invoke("convert pressure")
    )
    assert result.next == "general"
    path, body = compatible_api[-1]
    assert path == "/v1/chat/completions"
    assert body["stream"] is True
    assert body["tool_choice"]["function"]["name"] == "RouteDecision"


@pytest.mark.asyncio
async def test_stream_events_and_tool_execution(compatible_api):
    model = get_chat_llm().bind_tools([convert_unit])
    events = [event async for event in model.astream_events("convert pressure", version="v2")]
    assert any(event["event"] == "on_chat_model_stream" for event in events)
    result = next(e["data"]["output"] for e in events if e["event"] == "on_chat_model_end")
    assert isinstance(result, AIMessage)
    assert result.tool_calls[0]["name"] == "convert_unit"
    # 新版 ToolNode 由图注入 runtime, 与项目中的实际执行方式保持一致。
    builder = StateGraph(AgentState)
    builder.add_node("tools", ToolNode([convert_unit]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    output = await builder.compile().ainvoke({"messages": [result]})
    tool_result = output["messages"][-1]
    assert tool_result.tool_call_id == "call_test"
    assert "145.038" in tool_result.content
    answer = await get_chat_llm().ainvoke([HumanMessage("convert pressure"), result, tool_result])
    assert answer.content == "compatibility-ok"
    assert compatible_api[-1][1]["messages"][-1]["role"] == "tool"


def test_embedding_keeps_text_input_dimensions_and_batching(compatible_api):
    result = get_embedding().embed_documents(["first", "second", "third"])
    assert len(result) == 3
    assert all(len(vector) == 1024 for vector in result)
    assert [body["input"] for _, body in compatible_api] == [["first", "second"], ["third"]]
    assert all(body["dimensions"] == 1024 for _, body in compatible_api)
