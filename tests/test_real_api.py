"""
真实 API 冒烟测试（默认跳过）.

运行方式:
  PowerShell:  $env:RUN_REAL_API="1"; python -m pytest tests/test_real_api.py -v

需要项目根目录 .env 中配置真实 LLM_API_KEY。
这类测试会产生少量真实 token 消耗，因此默认不进入常规 CI 流程，
只在"真实环境联调"时手动开启。
"""

from __future__ import annotations

import os

import pytest

from dotenv import load_dotenv

load_dotenv()

_REAL_ENABLED = os.environ.get("RUN_REAL_API") == "1" and bool(os.environ.get("LLM_API_KEY"))

pytestmark = pytest.mark.skipif(
    not _REAL_ENABLED,
    reason="需要 RUN_REAL_API=1 且配置真实 LLM_API_KEY",
)


def _make_agent():
    from src.agent import Agent
    from src.llm_client import LLMClient
    from src.memory import ContextManager
    from src.sessions import SessionManager
    from src.tools import ToolRegistry
    from src.tools.calculator import CALCULATOR_TOOL
    from src.tools.search import SEARCH_TOOL
    from src.tools.todo_list import TODO_TOOL

    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)
    registry.register(SEARCH_TOOL)
    registry.register(TODO_TOOL)

    return Agent(
        llm=LLMClient(),
        tools=registry,
        session_manager=SessionManager(),
        context_manager=ContextManager(),
        max_steps=6,
    )


def test_real_direct_answer():
    """真实模型：纯对话，不需要工具."""
    agent = _make_agent()
    answer = agent.chat("real_1", "用一句话回答：1 加 1 等于几？")
    assert isinstance(answer, str) and answer.strip()
    assert "LLM 调用失败" not in answer, answer


def test_real_tool_call():
    """真实模型：应自主选择 calculator 工具并给出正确结果."""
    agent = _make_agent()
    answer = agent.chat("real_2", "请用计算器算出 1234 * 5678 的精确值")
    assert "LLM 调用失败" not in answer, answer
    assert "7006652" in answer.replace(",", ""), f"期望 7006652，实际: {answer}"


def test_real_multi_turn():
    """真实模型：同一 session 多轮追问，能记住上文."""
    agent = _make_agent()
    agent.chat("real_3", "记住一个数字：42。只回复「好的」。")
    answer = agent.chat("real_3", "刚才我让你记住的数字是多少？")
    assert "LLM 调用失败" not in answer, answer
    assert "42" in answer, f"多轮记忆失败，实际: {answer}"


def test_real_session_isolation():
    """真实模型：两个 session 上下文隔离."""
    agent = _make_agent()
    agent.chat("real_a", "记住：我的名字叫小明。只回复「记住了」。")
    answer = agent.chat("real_b", "我叫什么名字？如果不知道就说「不知道」。")
    assert "LLM 调用失败" not in answer, answer
    assert "小明" not in answer, f"session 隔离失败，另一个窗口看到了名字: {answer}"
