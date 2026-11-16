"""Web 适配层测试：真实 HTTP + 真实 Agent 核心，模型调用由 MockLLM 替代。"""

from __future__ import annotations

import http.client
import json
import threading
from typing import Any

import pytest

from src.agent import Agent
from src.llm_client import LLMResponse
from src.memory import ContextManager
from src.sessions import SessionManager
from src.tools import ToolRegistry
from src.tools.calculator import CALCULATOR_TOOL
from src.tools.search import SEARCH_TOOL
from src.tools.todo_list import TODO_TOOL
from web_server import create_server


class MockLLM:
    """默认直接回答，也允许单个测试预设工具调用序列。"""

    api_key = "sk-test-only"
    model = "mock-web-model"

    def __init__(self) -> None:
        self.responses: list[LLMResponse] = []

    def chat(self, messages, tools=None, system_prompt=None, temperature=0.7):
        if self.responses:
            return self.responses.pop(0)
        last_user = next(
            (message["content"] for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        return make_response(answer=f"Mock 回答: {last_user}")


def make_response(
    *,
    action: str = "final_answer",
    answer: str | None = None,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | None = None,
) -> LLMResponse:
    return LLMResponse(content=json.dumps({
        "thought": "Web 测试",
        "action": action,
        "answer": answer,
        "tool_name": tool_name,
        "tool_args": tool_args,
    }, ensure_ascii=False))


@pytest.fixture
def web_app():
    mock = MockLLM()
    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)
    registry.register(SEARCH_TOOL)
    registry.register(TODO_TOOL)
    agent = Agent(
        llm=mock,
        tools=registry,
        session_manager=SessionManager(),
        context_manager=ContextManager(),
        max_steps=10,
    )
    server = create_server("127.0.0.1", 0, agent)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield server, mock
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(
    server,
    method: str,
    path: str,
    body: Any = None,
    *,
    content_type: str = "application/json",
) -> tuple[int, dict[str, str], Any]:
    """用标准库发请求，避免测试引入 requests/httpx 客户端耦合。"""
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
    headers = {}
    payload = None
    if body is not None:
        payload = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = content_type
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    response_headers = {key.lower(): value for key, value in response.getheaders()}
    if response_headers.get("content-type", "").startswith("application/json"):
        parsed: Any = json.loads(raw.decode("utf-8"))
    else:
        parsed = raw.decode("utf-8")
    status = response.status
    connection.close()
    return status, response_headers, parsed


def test_static_resources_and_security_headers(web_app):
    server, _ = web_app
    for path in ("/", "/styles.css", "/api.js", "/app.js"):
        status, headers, content = request(server, "GET", path)
        assert status == 200
        assert content
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"

    status, headers, content = request(server, "GET", "/")
    assert "Minimal Agent" in content
    assert "default-src 'self'" in headers["content-security-policy"]


def test_health_and_tools_expose_public_metadata_only(web_app):
    server, _ = web_app
    status, _, health = request(server, "GET", "/api/health")
    assert status == 200
    assert health == {
        "status": "ok",
        "model": "mock-web-model",
        "llm_configured": True,
        "tool_count": 3,
    }
    assert "sk-test-only" not in json.dumps(health)

    status, _, payload = request(server, "GET", "/api/tools")
    assert status == 200
    assert {tool["name"] for tool in payload["tools"]} == {"calculator", "search", "todo_list"}
    assert all("parameters" in tool for tool in payload["tools"])


def test_session_create_list_and_read(web_app):
    server, _ = web_app
    status, _, created = request(server, "POST", "/api/sessions", {"session_id": "web-demo"})
    assert status == 201
    assert created["session"]["id"] == "web-demo"
    assert created["session"]["messages"] == []

    status, _, existing = request(server, "POST", "/api/sessions", {"session_id": "web-demo"})
    assert status == 200
    assert existing["session"]["id"] == "web-demo"

    status, _, sessions = request(server, "GET", "/api/sessions")
    assert status == 200
    assert sessions["sessions"][0]["id"] == "web-demo"

    status, _, session = request(server, "GET", "/api/sessions/web-demo")
    assert status == 200
    assert session["session"]["message_count"] == 0


def test_chat_uses_real_agent_and_returns_trace(web_app):
    server, _ = web_app
    status, _, payload = request(server, "POST", "/api/chat", {
        "session_id": "web-chat",
        "message": "你好",
    })
    assert status == 200
    assert payload["answer"] == "Mock 回答: 你好"
    session = payload["session"]
    assert [message["role"] for message in session["messages"]] == ["user", "assistant"]
    assert session["message_count"] == 2
    assert session["turns"] == 1
    assert any("Final Answer" in entry for entry in session["trace"])


def test_chat_supports_tool_call_round_trip(web_app):
    server, mock = web_app
    mock.responses = [
        make_response(action="tool_call", tool_name="calculator", tool_args={"expression": "6 * 7"}),
        make_response(answer="计算结果是 42。"),
    ]
    status, _, payload = request(server, "POST", "/api/chat", {
        "session_id": "web-tool",
        "message": "6 乘以 7 等于多少？",
    })
    assert status == 200
    assert payload["answer"] == "计算结果是 42。"
    roles = [message["role"] for message in payload["session"]["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert payload["session"]["messages"][1]["tool_calls"][0]["name"] == "calculator"
    assert "42" in payload["session"]["messages"][2]["content"]


def test_reset_clears_messages_but_keeps_trace(web_app):
    server, _ = web_app
    request(server, "POST", "/api/chat", {"session_id": "web-reset", "message": "保留轨迹"})
    status, _, payload = request(server, "POST", "/api/sessions/web-reset/reset", {})
    assert status == 200
    assert payload["session"]["messages"] == []
    assert payload["session"]["message_count"] == 0
    assert any("已重置" in entry for entry in payload["session"]["trace"])


@pytest.mark.parametrize("session_id", ["", "bad/id", ".hidden", "x" * 65])
def test_invalid_session_id_is_rejected(web_app, session_id):
    server, _ = web_app
    status, _, payload = request(server, "POST", "/api/chat", {
        "session_id": session_id,
        "message": "test",
    })
    assert status == 400
    assert payload["error"]["code"] == "invalid_session"


@pytest.mark.parametrize("message", ["", "   ", None, 123])
def test_empty_or_non_string_message_is_rejected(web_app, message):
    server, _ = web_app
    status, _, payload = request(server, "POST", "/api/chat", {
        "session_id": "web-validation",
        "message": message,
    })
    assert status == 400
    assert payload["error"]["code"] == "invalid_message"


def test_request_validation_and_missing_resources(web_app):
    server, _ = web_app
    status, _, payload = request(server, "POST", "/api/chat", b"not-json")
    assert status == 400
    assert payload["error"]["code"] == "invalid_json"

    status, _, payload = request(server, "POST", "/api/chat", "{}", content_type="text/plain")
    assert status == 415
    assert payload["error"]["code"] == "unsupported_media_type"

    status, _, payload = request(server, "GET", "/api/sessions/not-found")
    assert status == 404
    assert payload["error"]["code"] == "session_not_found"

    status, _, _ = request(server, "GET", "/..%2Fweb_server.py")
    assert status == 404


def test_message_length_limit(web_app):
    server, _ = web_app
    status, _, payload = request(server, "POST", "/api/chat", {
        "session_id": "web-limit",
        "message": "长" * 4001,
    })
    assert status == 400
    assert payload["error"]["code"] == "message_too_long"


def read_sse(server, path: str, body: dict[str, Any]) -> tuple[int, list[tuple[str, Any]]]:
    """读取一次性 SSE 响应（服务端发送 done 后关闭连接）。"""
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    connection.request(
        "POST",
        path,
        body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    raw = response.read().decode("utf-8")
    status = response.status
    connection.close()

    events: list[tuple[str, Any]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data += line[len("data: "):]
        events.append((event, json.loads(data) if data else None))
    return status, events


def test_chat_stream_emits_start_trace_and_done(web_app):
    server, _ = web_app
    status, events = read_sse(server, "/api/chat/stream", {
        "session_id": "web-stream",
        "message": "流式回答测试",
    })

    assert status == 200
    names = [name for name, _ in events]
    assert names[0] == "start"
    assert names[-1] == "done"
    assert "trace" in names

    trace_entries = [data["entry"] for name, data in events if name == "trace"]
    assert any("用户输入" in entry for entry in trace_entries)
    assert any("Final Answer" in entry for entry in trace_entries)

    done = events[-1][1]
    assert done["answer"] == "Mock 回答: 流式回答测试"
    assert done["session"]["message_count"] == 2
    assert done["elapsed"] >= 0


def test_chat_stream_rejects_invalid_message(web_app):
    server, _ = web_app
    status, _, payload = request(server, "POST", "/api/chat/stream", {
        "session_id": "web-stream-bad",
        "message": "   ",
    })
    assert status == 400
    assert payload["error"]["code"] == "invalid_message"


def test_delete_session(web_app):
    server, _ = web_app
    request(server, "POST", "/api/sessions", {"session_id": "web-delete"})

    status, _, payload = request(server, "DELETE", "/api/sessions/web-delete")
    assert status == 200
    assert payload == {"deleted": "web-delete"}

    status, _, payload = request(server, "GET", "/api/sessions/web-delete")
    assert status == 404
    assert payload["error"]["code"] == "session_not_found"

    status, _, payload = request(server, "DELETE", "/api/sessions/web-delete")
    assert status == 404
    assert payload["error"]["code"] == "session_not_found"


def test_host_header_validation(web_app):
    server, _ = web_app

    def call_with_host(host: str) -> tuple[int, dict[str, Any]]:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
        connection.putrequest("GET", "/api/health", skip_host=True)
        connection.putheader("Host", host)
        connection.endheaders()
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        status = response.status
        connection.close()
        return status, payload

    assert call_with_host("127.0.0.1:8080")[0] == 200
    assert call_with_host("localhost:8080")[0] == 200

    status, payload = call_with_host("evil.example.com")
    assert status == 403
    assert payload["error"]["code"] == "invalid_host"

