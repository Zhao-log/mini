"""
测试 Tool 系统 + 三个具体工具.

覆盖场景:
  ✓ ToolRegistry 注册 / 查找
  ✓ calculator: 正常计算
  ✓ calculator: 安全拦截（不允许 eval 危险表达式）
  ✓ calculator: 除零错误
  ✓ search: mock 数据匹配
  ✓ search: 空关键词 / 无结果
  ✓ todo_list: add/list/complete/remove 全流程
  ✓ Tool 不存在 → ToolNotFoundError
"""

import pytest

from src.exceptions import ToolExecutionError, ToolNotFoundError
from src.tools import Tool, ToolRegistry
from src.tools.calculator import CALCULATOR_TOOL, calculator_handler
from src.tools.search import SEARCH_TOOL, search_handler
from src.tools.todo_list import TODO_TOOL


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

def test_tool_registry_register_and_execute():
    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)

    assert "calculator" in registry.list_tools()

    result = registry.execute("calculator", {"expression": "2 + 3"})
    assert "5" in result


def test_tool_registry_not_found():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.execute("nonexistent", {})


def test_tool_registry_schema():
    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)

    schemas = registry.get_all_tools_schema()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "calculator"
    assert "parameters" in schemas[0]["function"]


# ---------------------------------------------------------------------------
# Calculator — 直接调 handler 验证计算正确性
# ---------------------------------------------------------------------------

class TestCalculator:
    def test_basic_arithmetic(self):
        assert calculator_handler("2 + 3") == "计算结果: 5"
        assert calculator_handler("10 - 4") == "计算结果: 6"
        assert calculator_handler("6 * 7") == "计算结果: 42"
        assert calculator_handler("20 / 4") == "计算结果: 5"

    def test_power_and_mod(self):
        assert calculator_handler("2 ** 10") == "计算结果: 1024"
        assert calculator_handler("10 % 3") == "计算结果: 1"

    def test_unary_ops(self):
        assert calculator_handler("-5 + 3") == "计算结果: -2"

    def test_functions(self):
        assert calculator_handler("sqrt(144)") == "计算结果: 12"
        assert calculator_handler("abs(-7)") == "计算结果: 7"
        assert calculator_handler("max(1, 5, 3)") == "计算结果: 5"

    def test_constants(self):
        result = calculator_handler("round(pi, 2)")
        assert "3.14" in result

    def test_expression_precedence(self):
        # 先乘后加
        assert calculator_handler("2 + 3 * 4") == "计算结果: 14"
        assert calculator_handler("(2 + 3) * 4") == "计算结果: 20"

    # 以下用 Tool.execute 验证异常被正确包装为 ToolExecutionError

    def test_division_by_zero(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="1 / 0")

    def test_syntax_error(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="2 +")

    def test_empty_expression(self):
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="")

    def test_security_block_import(self):
        """尝试 __import__ 应该被拦截."""
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="__import__('os').system('echo pwned')")

    def test_security_block_builtin(self):
        """调用 open 等 builtin 应该被拦截."""
        with pytest.raises(ToolExecutionError):
            CALCULATOR_TOOL.execute(expression="open('/etc/passwd')")


# ---------------------------------------------------------------------------
# Search (mock)
# ---------------------------------------------------------------------------

class TestSearch:
    def test_exact_match(self):
        result = search_handler("python")
        assert "Python" in result
        assert "Python 3.12" in result

    def test_case_insensitive(self):
        result = search_handler("AGENT")
        assert "AI Agent" in result

    def test_multi_word(self):
        result = search_handler("new york")
        assert "纽约" in result or "New York" in result

    def test_no_result(self):
        result = search_handler("asdfghjkl_qwerty_unique_not_found")
        assert "未找到" in result

    def test_empty_query(self):
        result = search_handler("")
        assert "不能为空" in result


# ---------------------------------------------------------------------------
# TodoList
# ---------------------------------------------------------------------------

class TestTodoList:
    def setup_method(self):
        """每个测试前重置 todo 状态."""
        import src.tools.todo_list as tl
        tl._state.clear()

    def test_add_and_list(self):
        result = TODO_TOOL.execute(action="add", item="写测试用例", session_id="test1")
        assert "已添加" in result
        assert "写测试用例" in result

        list_result = TODO_TOOL.execute(action="list", session_id="test1")
        assert "写测试用例" in list_result

    def test_complete(self):
        TODO_TOOL.execute(action="add", item="complete me", session_id="test2")
        result = TODO_TOOL.execute(action="complete", item="complete me", session_id="test2")
        assert "已完成" in result

    def test_remove(self):
        TODO_TOOL.execute(action="add", item="remove me", session_id="test3")
        result = TODO_TOOL.execute(action="remove", item="remove me", session_id="test3")
        assert "已删除" in result

        list_result = TODO_TOOL.execute(action="list", session_id="test3")
        assert "(空)" in list_result  # 只剩空了

    def test_list_empty(self):
        result = TODO_TOOL.execute(action="list", session_id="fresh_session")
        assert "(空)" in result

    def test_invalid_action(self):
        with pytest.raises(ToolExecutionError):
            TODO_TOOL.execute(action="invalid_action", session_id="test4")

    def test_sessions_isolation(self):
        """不同 session 的 todo 应该隔离."""
        TODO_TOOL.execute(action="add", item="only in s1", session_id="s1")

        s2_list = TODO_TOOL.execute(action="list", session_id="s2")
        assert "only in s1" not in s2_list
        assert "(空)" in s2_list
