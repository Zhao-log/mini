"""
边界条件与异常场景测试.

关注点:
  - 极端输入（超长、嵌套、特殊字符、空值）
  - 防御性校验（DoS、递归、类型错误）
  - 异常路径不泄露裸异常、不崩溃
"""

from __future__ import annotations

import json

import pytest

from src.agent import Agent
from src.exceptions import ToolExecutionError
from src.llm_client import LLMClient, LLMResponse
from src.memory import ContextManager
from src.parser import parse_llm_response
from src.sessions import SessionManager
from src.tools import ToolRegistry
from src.tools.calculator import CALCULATOR_TOOL, calculator_handler
from src.tools.search import search_handler
from src.tools.todo_list import TODO_TOOL


# ---------------------------------------------------------------------------
# 计算器：边界与攻击面
# ---------------------------------------------------------------------------

class TestCalculatorBoundary:
    def test_pow_dos_guard(self):
        """9**9**9 会造成 CPU DoS，必须被拦截."""
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="9**9**9")

    def test_pow_reasonable_still_works(self):
        assert calculator_handler("2 ** 64") == "计算结果: 18446744073709551616"

    def test_huge_base_guard(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="99999999 ** 999")

    def test_deep_nesting(self):
        """超深括号应受控失败，不应崩溃."""
        expr = "(" * 500 + "1" + ")" * 500
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression=expr)

    def test_string_constant_rejected(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="'abc'")

    def test_bool_constant_rejected(self):
        """bool 是 int 子类，必须显式拒绝，否则 True+1 会被算成 2."""
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="True + 1")

    def test_lambda_rejected(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="(lambda: 1)()")

    def test_attribute_access_rejected(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="().__class__")

    def test_nonexistent_function(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="foo(1)")

    def test_unicode_expression(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="一 加 一")

    def test_moderately_long_expression(self):
        expr = " + ".join(["1"] * 100)
        assert "100" in calculator_handler(expr)

    def test_extremely_long_expression_controlled(self):
        """极长链式表达式不能挂死，必须受控失败."""
        expr = " + ".join(["1"] * 5000)
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression=expr)

    def test_zero_division_variants(self):
        for expr in ("1/0", "1//0", "1%0"):
            with pytest.raises(ToolExecutionError):
                CALCULATOR_TOOL.execute(expression=expr)

    def test_missing_required_arg(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute()

    def test_extra_unknown_arg(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="1+1", unexpected="x")


# ---------------------------------------------------------------------------
# 搜索工具边界
# ---------------------------------------------------------------------------

class TestSearchBoundary:
    def test_whitespace_query(self):
        assert "不能为空" in search_handler("   ")

    def test_very_long_query(self):
        result = search_handler("x" * 10000)
        assert "未找到" in result

    def test_sql_injection_like_query(self):
        """不应该因为特殊字符崩溃."""
        result = search_handler("'; DROP TABLE users; --")
        assert isinstance(result, str)

    def test_unicode_query(self):
        assert isinstance(search_handler("天气"), str)


# ---------------------------------------------------------------------------
# todo 工具边界
# ---------------------------------------------------------------------------

class TestTodoBoundary:
    def setup_method(self):
        import src.tools.todo_list as tl
        tl._state.clear()

    def test_add_missing_item(self):
        with pytest.raises(ToolExecutionError):
            TODO_TOOL.execute(action="add")

    def test_complete_nonexistent(self):
        result = TODO_TOOL.execute(action="complete", item="不存在的事", session_id="b1")
        assert "未找到" in result

    def test_remove_by_id(self):
        TODO_TOOL.execute(action="add", item="任务A", session_id="b2")
        result = TODO_TOOL.execute(action="remove", item="1", session_id="b2")
        assert "已删除" in result

    def test_very_long_item(self):
        long_item = "长" * 5000
        result = TODO_TOOL.execute(action="add", item=long_item, session_id="b3")
        assert "已添加" in result


# ---------------------------------------------------------------------------
# Parser 边界
# ---------------------------------------------------------------------------

class TestParserBoundary:
    def test_empty_string(self):
        parsed = parse_llm_response("")
        assert parsed.action == "final_answer"

    def test_whitespace_only(self):
        parsed = parse_llm_response("   \n\t  ")
        assert parsed.action == "final_answer"

    def test_json_array_single(self):
        parsed = parse_llm_response('[{"action": "final_answer", "answer": "x"}]')
        assert parsed.action == "final_answer"
        assert parsed.final_answer == "x"

    def test_json_array_multiple(self):
        parsed = parse_llm_response('[{"a":1},{"b":2}]')
        assert parsed.action == "final_answer"

    def test_nested_json_in_text(self):
        raw = '说明：{"thought":"t","action":"final_answer","answer":"嵌套 {大括号} 内容"}'
        parsed = parse_llm_response(raw)
        assert parsed.action == "final_answer"

    def test_answer_with_markdown(self):
        raw = json.dumps({"action": "final_answer", "answer": "**粗体** 和 `代码`"}, ensure_ascii=False)
        parsed = parse_llm_response(raw)
        assert "**粗体**" in parsed.final_answer

    def test_tool_args_null(self):
        raw = json.dumps({"action": "tool_call", "tool_name": "calculator", "tool_args": None})
        parsed = parse_llm_response(raw)
        assert parsed.action == "tool_call"
        assert parsed.tool_args == {}

    def test_tool_args_list_rejected(self):
        raw = json.dumps({"action": "tool_call", "tool_name": "calculator", "tool_args": [1, 2]})
        parsed = parse_llm_response(raw)
        # 非 dict 的 tool_args 应被归一化为空 dict，而不是让下游炸
        assert isinstance(parsed.tool_args, dict)

    def test_unicode_payload(self):
        raw = json.dumps({"action": "final_answer", "answer": "🎉 中文 emoji"}, ensure_ascii=False)
        parsed = parse_llm_response(raw)
        assert "🎉" in parsed.final_answer

    def test_huge_payload(self):
        big = "x" * 200_000
        parsed = parse_llm_response(json.dumps({"action": "final_answer", "answer": big}))
        assert len(parsed.final_answer) == 200_000


# ---------------------------------------------------------------------------
# Session 边界
# ---------------------------------------------------------------------------

class TestSessionBoundary:
    def test_empty_session_id(self):
        sm = SessionManager()
        s = sm.get_or_create("")
        assert s.session_id == ""

    def test_unicode_session_id(self):
        sm = SessionManager()
        s = sm.get_or_create("窗口-一-🎯")
        assert s.session_id == "窗口-一-🎯"

    def test_many_sessions(self):
        sm = SessionManager()
        for i in range(500):
            sm.get_or_create(f"s{i}")
        assert len(sm.list_sessions()) == 500

    def test_reset_missing_session(self):
        sm = SessionManager()
        agent = Agent(
            llm=LLMClient(api_key="x"),
            tools=ToolRegistry(),
            session_manager=sm,
        )
        assert agent.reset_session("不存在") is False

    def test_get_trace_missing_session(self):
        agent = Agent(llm=LLMClient(api_key="x"), tools=ToolRegistry(), session_manager=SessionManager())
        assert "不存在" in agent.get_trace("nope")


# ---------------------------------------------------------------------------
# Context 边界
# ---------------------------------------------------------------------------

class TestContextBoundary:
    def test_max_rounds_one(self):
        cm = ContextManager()
        cm.MAX_ROUNDS = 1
        msgs = []
        for i in range(5):
            msgs.append({"role": "user", "content": f"u{i}"})
            msgs.append({"role": "assistant", "content": f"a{i}"})
        out = cm._truncate_by_rounds(msgs)
        assert len(out) == 2
        assert out[0]["role"] == "user"
        assert out[0]["content"] == "u4"

    def test_truncate_keeps_user_first(self):
        """截断后第一条必须是 user，不能出现孤立 assistant/tool."""
        cm = ContextManager()
        cm.MAX_ROUNDS = 1
        msgs = [
            {"role": "user", "content": "u0"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c0"}]},
            {"role": "tool", "tool_call_id": "c0", "content": "r0"},
            {"role": "assistant", "content": "a0"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]
        out = cm._truncate_by_rounds(msgs)
        assert out[0]["role"] == "user"
        assert out[0]["content"] == "u1"

    def test_compress_merges_system(self):
        """压缩产生 system 摘要时，不应出现两条 system."""
        cm = ContextManager()
        cm.MAX_CHARS = 100
        cm.COMPRESS_THRESHOLD = 60
        msgs = []
        for i in range(20):
            msgs.append({"role": "user", "content": "问题" * 50})
            msgs.append({"role": "assistant", "content": "回答" * 50})
        out = cm.build_context(msgs, system_prompt="SYS")
        system_count = sum(1 for m in out if m.get("role") == "system")
        assert system_count == 1

    def test_empty_messages_no_system(self):
        cm = ContextManager()
        assert cm.build_context([]) == []

    def test_filter_missing_content(self):
        cm = ContextManager()
        out = cm._filter_messages([{"role": "user"}])
        assert out[0]["content"] == ""


# ---------------------------------------------------------------------------
# Agent 异常路径
# ---------------------------------------------------------------------------

class _ScriptedLLM:
    def __init__(self, contents: list[str]):
        self.contents = list(reversed(contents))

    def chat(self, messages, tools=None, system_prompt=None, temperature=0.7):
        if not self.contents:
            return LLMResponse(content=json.dumps({"action": "final_answer", "answer": "done"}))
        return LLMResponse(content=self.contents.pop())


def _agent_with(llm, tools=None, max_steps=10):
    return Agent(
        llm=llm,
        tools=tools or ToolRegistry(),
        session_manager=SessionManager(),
        context_manager=ContextManager(),
        max_steps=max_steps,
    )


class TestAgentExceptionPaths:
    def test_empty_user_input(self):
        agent = _agent_with(_ScriptedLLM([json.dumps({"action": "final_answer", "answer": "ok"})]))
        assert agent.chat("s", "") == "ok"

    def test_very_long_user_input(self):
        long_input = "很长的问题" * 20000
        agent = _agent_with(_ScriptedLLM([json.dumps({"action": "final_answer", "answer": "ok"})]))
        assert agent.chat("s", long_input) == "ok"
        assert len(agent.session_manager.get("s").messages[0]["content"]) == len(long_input)

    def test_llm_raises_exception(self):
        class BoomLLM:
            def chat(self, *a, **kw):
                raise RuntimeError("network down")

        agent = _agent_with(BoomLLM())
        result = agent.chat("s", "hi")
        assert "LLM 调用失败" in result
        # session 里不应留下半截状态导致后续不可用
        assert agent.session_manager.exists("s")

    def test_tool_raises_unexpected_exception(self):
        """工具内部抛非预期异常时，Agent 不应崩溃."""
        from src.tools import Tool

        def boom(**kwargs):
            raise ValueError("工具内部炸了")

        registry = ToolRegistry()
        registry.register(Tool(name="boom", description="d",
                               parameters={"type": "object", "properties": {}},
                               handler=boom))
        llm = _ScriptedLLM([
            json.dumps({"action": "tool_call", "tool_name": "boom", "tool_args": {}}),
            json.dumps({"action": "final_answer", "answer": "工具挂了，我直接回答"}),
        ])
        agent = _agent_with(llm, registry)
        result = agent.chat("s", "试试")
        assert "工具挂了" in result

    def test_max_steps_one(self):
        llm = _ScriptedLLM([json.dumps({"action": "tool_call", "tool_name": "nope", "tool_args": {}})] * 5)
        agent = _agent_with(llm, max_steps=1)
        assert "最大步数" in agent.chat("s", "hi")

    def test_tool_result_not_string(self):
        """工具返回非字符串时应被 str() 化，不能污染 context."""
        from src.tools import Tool

        registry = ToolRegistry()
        registry.register(Tool(name="num", description="d",
                               parameters={"type": "object", "properties": {}},
                               handler=lambda: 42))
        llm = _ScriptedLLM([
            json.dumps({"action": "tool_call", "tool_name": "num", "tool_args": {}}),
            json.dumps({"action": "final_answer", "answer": "ok"}),
        ])
        agent = _agent_with(llm, registry)
        assert agent.chat("s", "hi") == "ok"
        tool_msgs = [m for m in agent.session_manager.get("s").messages if m.get("role") == "tool"]
        assert tool_msgs[0]["content"] == "42"


# ---------------------------------------------------------------------------
# LLMClient 消息归一化边界
# ---------------------------------------------------------------------------

class TestLLMClientNormalization:
    def test_native_format_passthrough(self):
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "f", "arguments": '{"a":1}'},
            }],
        }]
        out = LLMClient._normalize_messages(msgs)
        tc = out[0]["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["function"]["arguments"] == '{"a":1}'

    def test_internal_format_converted(self):
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "f", "arguments": {"a": 1}}],
        }]
        out = LLMClient._normalize_messages(msgs)
        tc = out[0]["tool_calls"][0]
        assert tc["type"] == "function"
        assert json.loads(tc["function"]["arguments"]) == {"a": 1}

    def test_missing_id_generated(self):
        msgs = [{
            "role": "assistant", "content": "",
            "tool_calls": [{"name": "f", "arguments": {}}],
        }]
        out = LLMClient._normalize_messages(msgs)
        assert out[0]["tool_calls"][0]["id"]

    def test_tool_message_stringified(self):
        out = LLMClient._normalize_messages([{"role": "tool", "tool_call_id": "c", "content": 123}])
        assert out[0]["content"] == "123"

    def test_content_list_coerced(self):
        msg = {"content": [{"type": "text", "text": "hi"}, " there"]}
        assert LLMClient._coerce_content(msg) == "hi there"

    def test_content_none_with_native_tool_calls(self):
        msg = {"content": None, "tool_calls": [{
            "id": "c", "type": "function",
            "function": {"name": "calculator", "arguments": '{"expression":"1+1"}'},
        }]}
        parsed = parse_llm_response(LLMClient._coerce_content(msg))
        assert parsed.action == "tool_call"
        assert parsed.tool_name == "calculator"

    def test_content_none_no_tool_calls(self):
        parsed = parse_llm_response(LLMClient._coerce_content({"content": None}))
        assert parsed.action == "final_answer"

    def test_invalid_arguments_json(self):
        msg = {"content": None, "tool_calls": [{
            "id": "c", "type": "function",
            "function": {"name": "f", "arguments": "not-json"},
        }]}
        # 不应抛异常
        assert isinstance(LLMClient._coerce_content(msg), str)

    def test_no_api_key_warns_only(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        client = LLMClient(api_key="")
        assert client.api_key == ""
