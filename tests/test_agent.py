"""
测试 Agent 核心循环.

用 MockLLM 代替真实 LLM，确保测试不需要 API Key.

覆盖场景（全是题目明确要求的功能点）:
  ✓ 直接回复（不用工具）
  ✓ 调用 calculator 工具
  ✓ 调用 search 工具
  ✓ 工具调用失败 → Agent 返回错误信息
  ✓ 多步循环（LLM 先调工具再回答）
  ✓ 追问场景（同 session 多轮对话）
  ✓ 不同 session 隔离（各自 messages 独立）
  ✓ 达到 max_steps → 返回限制提示
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# Mock LLM —— 按预设的 response 序列返回
# ---------------------------------------------------------------------------

@dataclass
class MockLLM:
    """可以预设 LLM 返回序列，每轮 chat() 依次 pop 一个."""
    responses: list[LLMResponse] | None = None
    call_log: list[dict] = None

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(reversed(responses))
        self.call_log: list[dict] = []

    def chat(self, messages, tools=None, system_prompt=None, temperature=0.7):
        self.call_log.append({
            "messages_count": len(messages),
            "last_user": next((m["content"] for m in reversed(messages) if m.get("role") == "user"), ""),
            "has_tools": bool(tools),
        })
        if not self.responses:
            return LLMResponse(
                content=json.dumps({
                    "thought": "没有更多预设响应了",
                    "action": "final_answer",
                    "tool_name": None,
                    "tool_args": None,
                    "answer": "(mock LLM 耗尽)",
                }),
            )
        return self.responses.pop()


def make_response(*, thought: str, action: str, tool_name: str | None = None,
                  tool_args: dict | None = None, answer: str | None = None) -> LLMResponse:
    return LLMResponse(
        content=json.dumps({
            "thought": thought,
            "action": action,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "answer": answer,
        }),
    )


def build_agent_with_mock(mock_llm: MockLLM) -> Agent:
    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)
    registry.register(SEARCH_TOOL)
    registry.register(TODO_TOOL)

    return Agent(
        llm=mock_llm,
        tools=registry,
        session_manager=SessionManager(),
        context_manager=ContextManager(),
        max_steps=10,
    )


# ---------------------------------------------------------------------------
# 测试：直接回答
# ---------------------------------------------------------------------------

def test_direct_answer():
    mock = MockLLM([
        make_response(
            thought="直接回答就好",
            action="final_answer",
            answer="北京是中国的首都。",
        ),
    ])
    agent = build_agent_with_mock(mock)

    result = agent.chat("s1", "北京在哪？")

    assert "北京" in result
    assert len(mock.call_log) == 1


# ---------------------------------------------------------------------------
# 测试：调用 calculator
# ---------------------------------------------------------------------------

def test_tool_call_calculator():
    mock = MockLLM([
        make_response(
            thought="需要计算 123 * 456",
            action="tool_call",
            tool_name="calculator",
            tool_args={"expression": "123 * 456"},
        ),
        make_response(
            thought="计算完成，返回结果",
            action="final_answer",
            answer="123 × 456 = 56088",
        ),
    ])
    agent = build_agent_with_mock(mock)

    result = agent.chat("s1", "算一下 123 * 456")

    assert "56088" in result or "56088" in result
    assert len(mock.call_log) == 2


# ---------------------------------------------------------------------------
# 测试：调用 search
# ---------------------------------------------------------------------------

def test_tool_call_search():
    mock = MockLLM([
        make_response(
            thought="需要搜索 AI Agent 的信息",
            action="tool_call",
            tool_name="search",
            tool_args={"query": "agent"},
        ),
        make_response(
            thought="搜索到了相关结果",
            action="final_answer",
            answer="AI Agent 是能够自主规划、调用工具的智能体。",
        ),
    ])
    agent = build_agent_with_mock(mock)

    result = agent.chat("s1", "什么是 AI Agent？")

    assert "Agent" in result or "智能体" in result


# ---------------------------------------------------------------------------
# 测试：工具调用失败
# ---------------------------------------------------------------------------

def test_tool_not_found():
    mock = MockLLM([
        make_response(
            thought="试试不存在的工具",
            action="tool_call",
            tool_name="nonexistent_tool_xyz",
            tool_args={},
        ),
        make_response(
            thought="工具不存在，我直接回答吧",
            action="final_answer",
            answer="那个工具不可用，我直接告诉你...",
        ),
    ])
    agent = build_agent_with_mock(mock)

    result = agent.chat("s1", "测试不存在的工具")

    assert len(mock.call_log) == 2
    session = agent.session_manager.get("s1")
    assert any("不存在" in m.get("content", "") for m in session.messages)


# ---------------------------------------------------------------------------
# 测试：多轮追问（同 session）
# ---------------------------------------------------------------------------

def test_multi_turn_conversation():
    """同 session 两次 chat，session 里应该累积 >= 4 条消息."""
    mock = MockLLM([
        make_response(
            thought="直接回答",
            action="final_answer",
            answer="第一次的回答",
        ),
        make_response(
            thought="追问一下",
            action="final_answer",
            answer="第二次的回答",
        ),
    ])
    agent = build_agent_with_mock(mock)

    agent.chat("persistent_session", "第一问")
    agent.chat("persistent_session", "那它的细节呢？")

    assert len(mock.call_log) == 2
    session = agent.session_manager.get("persistent_session")
    # 至少 user+assistant+user+assistant = 4 条
    assert len(session.messages) >= 4


# ---------------------------------------------------------------------------
# 测试：session 隔离
# ---------------------------------------------------------------------------

def test_session_isolation():
    """两个不同 session 各自的 messages 数量应该独立."""
    mock = MockLLM([
        make_response(thought="ok", action="final_answer", answer="窗口2的回答"),
        make_response(thought="ok", action="final_answer", answer="窗口1的回答"),
    ])
    agent = build_agent_with_mock(mock)

    agent.chat("window_1", "窗口1的问题")
    agent.chat("window_2", "窗口2的问题")

    s1 = agent.session_manager.get("window_1")
    s2 = agent.session_manager.get("window_2")

    # 各自都有 user + assistant 两条
    assert len(s1.messages) >= 2
    assert len(s2.messages) >= 2

    # 窗口1的 user content 不应该出现在窗口2的 messages 里（mock 顺序反了）
    # 检查各自的 user 消息是对的
    s1_users = [m["content"] for m in s1.messages if m.get("role") == "user"]
    s2_users = [m["content"] for m in s2.messages if m.get("role") == "user"]
    assert s1_users == ["窗口1的问题"]
    assert s2_users == ["窗口2的问题"]


# ---------------------------------------------------------------------------
# 测试：达到 max_steps
# ---------------------------------------------------------------------------

def test_max_steps_exceeded():
    responses = [
        make_response(thought="调工具", action="tool_call",
                      tool_name="calculator", tool_args={"expression": "1+1"})
        for _ in range(20)
    ]
    mock = MockLLM(responses)
    agent = build_agent_with_mock(mock)
    agent.max_steps = 3

    result = agent.chat("s_overflow", "无限循环测试")

    assert "达到最大步数" in result
    assert len(mock.call_log) == 3
    # 超步数提示必须写入会话消息，保证刷新后回答仍然存在
    session = agent.session_manager.get("s_overflow")
    assert session is not None
    last = session.get_messages()[-1]
    assert last["role"] == "assistant"
    assert "达到最大步数" in last["content"]


# ---------------------------------------------------------------------------
# 测试：完整 trace
# ---------------------------------------------------------------------------

def test_trace_recorded():
    mock = MockLLM([
        make_response(thought="调用工具", action="tool_call",
                      tool_name="calculator", tool_args={"expression": "2+2"}),
        make_response(thought="有结果了", action="final_answer", answer="4"),
    ])
    agent = build_agent_with_mock(mock)

    agent.chat("s_trace", "trace 测试")

    trace = agent.get_trace("s_trace")
    assert "Step 1" in trace
    assert "Step 2" in trace
    assert "calculator" in trace
    assert "Final Answer" in trace


# ---------------------------------------------------------------------------
# 测试：reset session
# ---------------------------------------------------------------------------

def test_reset_session():
    mock = MockLLM([
        make_response(thought="ok", action="final_answer", answer="hello"),
    ])
    agent = build_agent_with_mock(mock)

    agent.chat("s_reset", "第一句")
    agent.chat("s_reset", "第二句")

    session = agent.session_manager.get("s_reset")
    assert len(session.messages) >= 4

    agent.reset_session("s_reset")
    session = agent.session_manager.get("s_reset")
    assert len(session.messages) == 0
