"""
集成测试 —— 使用本地真实 HTTP 服务模拟 OpenAI 兼容接口.

目的:
  1. 验证 LLMClient 发出的请求体完全符合 OpenAI Chat Completions 契约
  2. 验证多轮工具调用时 assistant.tool_calls / tool 两种消息的线上格式
  3. 打通 Agent → LLMClient → HTTP → Parser → ToolRegistry → Session 全链路
  4. 验证多 session 在真实链路上的隔离性

与单元测试的区别: 这里用真实 socket + 真实 HTTP 往返,
mock 只发生在"模型供给方", 而不是"传输层".
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from src.agent import Agent
from src.llm_client import LLMClient
from src.memory import ContextManager
from src.sessions import SessionManager
from src.tools import ToolRegistry
from src.tools.calculator import CALCULATOR_TOOL
from src.tools.search import SEARCH_TOOL
from src.tools.todo_list import TODO_TOOL


# ---------------------------------------------------------------------------
# 严格校验：模拟真实 OpenAI 服务端的消息格式校验
# ---------------------------------------------------------------------------

class ProtocolViolation(Exception):
    """请求体不符合 OpenAI 契约."""


def validate_openai_messages(messages: list[dict[str, Any]]) -> None:
    """
    按 OpenAI 官方契约严格校验 messages.
    
    真实服务端会因为这些原因返回 400，所以这里也判失败:
      - assistant.tool_calls[].type 必须为 "function"
      - assistant.tool_calls[].function.arguments 必须是 JSON 字符串（不能是 dict）
      - tool 消息的 tool_call_id 必须能对应到之前的 assistant tool_call
    """
    if not isinstance(messages, list):
        raise ProtocolViolation("messages 必须是 list")

    open_call_ids: set[str] = set()

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ProtocolViolation(f"messages[{idx}] 不是对象")

        role = msg.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            raise ProtocolViolation(f"messages[{idx}].role 非法: {role!r}")

        if "content" not in msg:
            raise ProtocolViolation(f"messages[{idx}] 缺少 content 字段")

        content = msg["content"]
        if content is not None and not isinstance(content, str):
            raise ProtocolViolation(
                f"messages[{idx}].content 必须是 string 或 null，实际 {type(content).__name__}"
            )

        if role == "assistant" and msg.get("tool_calls") is not None:
            tool_calls = msg["tool_calls"]
            if not isinstance(tool_calls, list) or not tool_calls:
                raise ProtocolViolation(f"messages[{idx}].tool_calls 必须是非空 list")

            for tc_idx, tc in enumerate(tool_calls):
                if not isinstance(tc, dict):
                    raise ProtocolViolation(f"messages[{idx}].tool_calls[{tc_idx}] 不是对象")
                if not isinstance(tc.get("id"), str) or not tc["id"]:
                    raise ProtocolViolation(f"messages[{idx}].tool_calls[{tc_idx}] 缺少合法 id")
                if tc.get("type") != "function":
                    raise ProtocolViolation(
                        f"messages[{idx}].tool_calls[{tc_idx}].type 必须为 'function'，"
                        f"实际 {tc.get('type')!r}"
                    )
                fn = tc.get("function")
                if not isinstance(fn, dict):
                    raise ProtocolViolation(
                        f"messages[{idx}].tool_calls[{tc_idx}] 缺少 function 对象"
                    )
                if not isinstance(fn.get("name"), str) or not fn["name"]:
                    raise ProtocolViolation(
                        f"messages[{idx}].tool_calls[{tc_idx}].function.name 非法"
                    )
                args = fn.get("arguments")
                if not isinstance(args, str):
                    raise ProtocolViolation(
                        f"messages[{idx}].tool_calls[{tc_idx}].function.arguments "
                        f"必须是 JSON 字符串，实际 {type(args).__name__}"
                    )
                try:
                    json.loads(args)
                except json.JSONDecodeError:
                    raise ProtocolViolation(
                        f"messages[{idx}].tool_calls[{tc_idx}].function.arguments 不是合法 JSON"
                    )
                open_call_ids.add(tc["id"])

        if role == "tool":
            tcid = msg.get("tool_call_id")
            if not isinstance(tcid, str) or not tcid:
                raise ProtocolViolation(f"messages[{idx}] role=tool 缺少 tool_call_id")
            if tcid not in open_call_ids:
                raise ProtocolViolation(
                    f"messages[{idx}] tool_call_id={tcid!r} 找不到对应的 assistant tool_call"
                )
            open_call_ids.discard(tcid)


# ---------------------------------------------------------------------------
# 假 OpenAI 服务端
# ---------------------------------------------------------------------------

class FakeOpenAIHandler(BaseHTTPRequestHandler):
    """
    最小 OpenAI 兼容服务端.
    
    通过 server.script 预设每个请求返回的 message 内容；
    server.requests 记录收到的每个请求体，供断言使用。
    """

    server_version = "FakeOpenAI/1.0"

    def log_message(self, fmt, *args):  # 静默
        pass

    def do_POST(self):
        srv = self.server
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_error(400, f"invalid json body: {e}")
            return

        record = {
            "path": self.path,
            "auth": self.headers.get("Authorization", ""),
            "content_type": self.headers.get("Content-Type", ""),
            "body": body,
            "validation_error": None,
        }

        # 严格校验 messages 契约
        try:
            validate_openai_messages(body.get("messages", []))
        except ProtocolViolation as e:
            record["validation_error"] = str(e)
            srv.requests.append(record)
            self._send_error(
                400,
                str(e),
                error_type="invalid_request_error",
                code="invalid_messages",
            )
            return

        srv.requests.append(record)

        # 预设的下一个响应
        if not srv.script:
            self._send_error(500, "no more scripted responses")
            return

        # 模拟供应商不支持 response_format=json_object:
        # 带该字段返回 400，去掉后正常返回
        if srv.script[0].get("_reject_response_format"):
            if "response_format" in body:
                self._send_error(
                    400,
                    "response_format is not supported by this model",
                    error_type="invalid_request_error",
                )
                return
            srv.script.pop(0)

        item = srv.script.pop(0)

        if item.get("_http_error"):
            self._send_error(
                item.get("_status", 500),
                item.get("_http_error"),
                error_type=item.get("_type", "server_error"),
            )
            return

        message = {"role": "assistant"}
        message.update(item)

        payload = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 0,
            "model": body.get("model", "fake"),
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send_error(404, "not found")

    def _send_error(self, status, msg, error_type="invalid_request_error", code=None):
        payload = {
            "error": {
                "message": msg,
                "type": error_type,
                "code": code,
            }
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def fake_openai():
    """启动一个本地假 OpenAI 服务，返回 (base_url, server)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
    server.script = []
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}/v1", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def build_agent(base_url: str, max_steps: int = 10) -> Agent:
    llm = LLMClient(base_url=base_url, api_key="sk-fake-test-key", model="fake-model", timeout=10)
    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)
    registry.register(SEARCH_TOOL)
    registry.register(TODO_TOOL)
    return Agent(
        llm=llm,
        tools=registry,
        session_manager=SessionManager(),
        context_manager=ContextManager(),
        max_steps=max_steps,
    )


def tool_call_message(name: str, args: dict, *, thought: str = "需要调用工具") -> dict:
    """构造一个"模型按我们协议输出 tool_call"的 content."""
    return {
        "content": json.dumps(
            {
                "thought": thought,
                "action": "tool_call",
                "tool_name": name,
                "tool_args": args,
                "answer": None,
            },
            ensure_ascii=False,
        )
    }


def final_message(answer: str, *, thought: str = "可以回答了") -> dict:
    return {
        "content": json.dumps(
            {
                "thought": thought,
                "action": "final_answer",
                "tool_name": None,
                "tool_args": None,
                "answer": answer,
            },
            ensure_ascii=False,
        )
    }


# ---------------------------------------------------------------------------
# IT-01 请求契约
# ---------------------------------------------------------------------------

def test_it01_request_contract(fake_openai):
    """验证请求头、路径、body 关键字段符合 OpenAI 契约."""
    base_url, server = fake_openai
    server.script.append(final_message("你好"))

    agent = build_agent(base_url)
    agent.chat("s1", "你好")

    assert len(server.requests) == 1
    req = server.requests[0]

    assert req["path"] == "/v1/chat/completions"
    assert req["auth"] == "Bearer sk-fake-test-key"
    assert "application/json" in req["content_type"]

    body = req["body"]
    assert body["model"] == "fake-model"
    assert body["response_format"] == {"type": "json_object"}
    assert body["tool_choice"] == "auto"
    assert isinstance(body["tools"], list) and len(body["tools"]) == 3
    for t in body["tools"]:
        assert t["type"] == "function"
        assert "name" in t["function"] and "parameters" in t["function"]

    # 第一条必须是 system，且包含工具描述
    assert body["messages"][0]["role"] == "system"
    assert "calculator" in body["messages"][0]["content"]
    assert req["validation_error"] is None


# ---------------------------------------------------------------------------
# IT-02 单次工具调用全链路
# ---------------------------------------------------------------------------

def test_it02_single_tool_roundtrip(fake_openai):
    """Agent 调 calculator → 拿到工具结果 → 给出最终答案."""
    base_url, server = fake_openai
    server.script.append(tool_call_message("calculator", {"expression": "123 * 456"}))
    server.script.append(final_message("123 × 456 = 56088"))

    agent = build_agent(base_url)
    answer = agent.chat("s1", "算一下 123*456")

    assert "56088" in answer
    assert len(server.requests) == 2

    # 第一次请求：只有 system + user
    first = server.requests[0]["body"]["messages"]
    assert [m["role"] for m in first] == ["system", "user"]

    # 第二次请求：应包含 assistant(tool_calls) + tool(result)
    second = server.requests[1]["body"]["messages"]
    roles = [m["role"] for m in second]
    assert roles == ["system", "user", "assistant", "tool"], f"实际 roles={roles}"

    # ⭐ 关键：第二次请求的 assistant.tool_calls 必须是 OpenAI 格式
    assistant_msg = second[2]
    assert server.requests[1]["validation_error"] is None, (
        f"服务端拒绝了请求: {server.requests[1]['validation_error']}"
    )
    tc = assistant_msg["tool_calls"][0]
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "calculator"
    assert isinstance(tc["function"]["arguments"], str)

    # tool 结果必须回到 tool message，且内容是真实计算结果
    tool_msg = second[3]
    assert "56088" in tool_msg["content"]
    assert tool_msg["tool_call_id"] == tc["id"]


# ---------------------------------------------------------------------------
# IT-03 多步工具链
# ---------------------------------------------------------------------------

def test_it03_multi_step_chain(fake_openai):
    """calculator → search → final，验证 3 步循环."""
    base_url, server = fake_openai
    server.script.append(tool_call_message("calculator", {"expression": "2 ** 10"}))
    server.script.append(tool_call_message("search", {"query": "python"}))
    server.script.append(final_message("1024，并且搜到了 Python 的资料"))

    agent = build_agent(base_url)
    answer = agent.chat("s1", "2 的 10 次方是多少？顺便查一下 python")

    assert "1024" in answer
    assert len(server.requests) == 3
    for i, req in enumerate(server.requests):
        assert req["validation_error"] is None, f"第 {i+1} 次请求被拒绝: {req['validation_error']}"

    # 最后一次请求应包含两轮工具调用记录
    final_msgs = server.requests[2]["body"]["messages"]
    roles = [m["role"] for m in final_msgs]
    assert roles.count("tool") == 2
    assert roles.count("assistant") == 2


# ---------------------------------------------------------------------------
# IT-04 服务端错误 → Agent 优雅降级
# ---------------------------------------------------------------------------

def test_it04_upstream_500_graceful(fake_openai):
    """上游 500，Agent 不崩溃，返回错误提示并落 trace."""
    base_url, server = fake_openai
    server.script.append({"_http_error": "internal error", "_status": 500})

    agent = build_agent(base_url)
    answer = agent.chat("s1", "你好")

    assert "LLM 调用失败" in answer
    trace = agent.get_trace("s1")
    assert "LLM 调用失败" in trace


def test_it05_upstream_401_graceful(fake_openai):
    """密钥无效（401），应给出可读错误而不是抛裸异常."""
    base_url, server = fake_openai
    server.script.append({"_http_error": "invalid api key", "_status": 401, "_type": "invalid_request_error"})

    agent = build_agent(base_url)
    answer = agent.chat("s1", "你好")

    assert "401" in answer or "LLM 调用失败" in answer


# ---------------------------------------------------------------------------
# IT-06 session 隔离（真实链路）
# ---------------------------------------------------------------------------

def test_it06_session_isolation_over_http(fake_openai):
    """两个 session 的上下文不能互相污染."""
    base_url, server = fake_openai
    server.script.append(final_message("窗口一的回答"))
    server.script.append(final_message("窗口二的回答"))

    agent = build_agent(base_url)
    agent.chat("window_1", "窗口一的问题")
    agent.chat("window_2", "窗口二的问题")

    assert len(server.requests) == 2

    msgs1 = server.requests[0]["body"]["messages"]
    msgs2 = server.requests[1]["body"]["messages"]

    text1 = json.dumps(msgs1, ensure_ascii=False)
    text2 = json.dumps(msgs2, ensure_ascii=False)

    assert "窗口一" in text1 and "窗口二" not in text1
    assert "窗口二" in text2 and "窗口一" not in text2


# ---------------------------------------------------------------------------
# IT-07 todo 工具的跨 session 状态隔离（端到端）
# ---------------------------------------------------------------------------

def test_it07_todo_state_isolated_between_sessions(fake_openai):
    """
    在 window_1 里让 Agent 添加待办，然后在 window_2 里查询待办.
    window_2 不应看到 window_1 的待办（session 隔离要求）.
    """
    base_url, server = fake_openai

    # window_1: 添加待办
    server.script.append(tool_call_message("todo_list", {"action": "add", "item": "给老板写周报"}))
    server.script.append(final_message("已为你添加待办"))

    # window_2: 查询待办
    server.script.append(tool_call_message("todo_list", {"action": "list"}))
    server.script.append(final_message("你的待办是空的"))

    agent = build_agent(base_url)

    agent.chat("window_1", "帮我加一个待办：给老板写周报")
    agent.chat("window_2", "看看我有什么待办")

    # window_1 占前 2 个请求（tool_call 决策 + 最终总结），
    # window_2 占后 2 个请求。检查 window_2 的两条请求里所有工具结果都看不到窗口一的待办。
    assert len(server.requests) == 4

    w2_tool_contents: list[str] = []
    for req in server.requests[2:]:
        for m in req["body"]["messages"]:
            if m.get("role") == "tool":
                w2_tool_contents.append(m.get("content", ""))

    assert w2_tool_contents, "window_2 没有产生任何工具结果消息"
    listed = "\n".join(w2_tool_contents)

    assert "给老板写周报" not in listed, (
        f"window_2 看到了 window_1 的待办，session 隔离失败: {listed}"
    )


# ---------------------------------------------------------------------------
# IT-08 模型返回原生 tool_calls（而非我们的 JSON 协议）
# ---------------------------------------------------------------------------

def test_it08_native_tool_calls_response(fake_openai):
    """模型返回 OpenAI 原生 tool_calls + content=null，也应被正确解析."""
    base_url, server = fake_openai
    server.script.append({
        "content": None,
        "tool_calls": [{
            "id": "call_native_1",
            "type": "function",
            "function": {"name": "calculator", "arguments": json.dumps({"expression": "7 * 8"})},
        }],
    })
    server.script.append(final_message("56"))

    agent = build_agent(base_url)
    answer = agent.chat("s1", "7 乘 8")

    assert "56" in answer
    assert len(server.requests) == 2
    assert server.requests[1]["validation_error"] is None


# ---------------------------------------------------------------------------
# IT-09 模型输出被 markdown 代码块包裹
# ---------------------------------------------------------------------------

def test_it09_markdown_wrapped_json(fake_openai):
    base_url, server = fake_openai
    raw = "```json\n" + json.dumps(
        {"thought": "ok", "action": "final_answer", "tool_name": None,
         "tool_args": None, "answer": "被包裹的回答"},
        ensure_ascii=False,
    ) + "\n```"
    server.script.append({"content": raw})

    agent = build_agent(base_url)
    answer = agent.chat("s1", "测试")

    assert "被包裹的回答" in answer


# ---------------------------------------------------------------------------
# IT-10 中文与特殊字符往返（编码兼容）
# ---------------------------------------------------------------------------

def test_it10_unicode_roundtrip(fake_openai):
    base_url, server = fake_openai
    payload = "你好，世界！🎉 特殊字符：<>&\"'\\n\\t"
    server.script.append(final_message(payload))

    agent = build_agent(base_url)
    answer = agent.chat("s1", "请原样返回：你好，世界！🎉")

    assert answer == payload
    # 请求体里的中文必须正确编码
    sent = server.requests[0]["body"]["messages"][-1]["content"]
    assert "你好，世界" in sent


# ---------------------------------------------------------------------------
# IT-11 供应商不支持 response_format 时自动降级
# ---------------------------------------------------------------------------

def test_it11_response_format_fallback(fake_openai):
    """
    部分本地模型/兼容网关不支持 response_format=json_object，会返回 400。
    LLMClient 应自动去掉该字段重试一次，而不是直接失败。
    """
    base_url, server = fake_openai
    server.script.append({"_reject_response_format": True})
    server.script.append(final_message("降级后依然成功"))

    agent = build_agent(base_url)
    answer = agent.chat("s1", "你好")

    assert "降级后依然成功" in answer
    assert len(server.requests) == 2
    assert "response_format" in server.requests[0]["body"]
    assert "response_format" not in server.requests[1]["body"]
