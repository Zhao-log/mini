"""
测试 Parser — LLM 输出解析.

覆盖场景:
  ✓ 正确解析 tool_call JSON
  ✓ 正确解析 final_answer JSON
  ✓ 解析 ```json ``` 代码块包裹的 JSON
  ✓ 解析非法 JSON → 降级为 final_answer
  ✓ 解析缺少 tool_name 的 tool_call → 降级
  ✓ 普通文本 → 降级为 final_answer
"""

import pytest

from src.parser import parse_llm_response


def test_parse_tool_call_json():
    raw = '{"thought": "需要计算一下", "action": "tool_call", "tool_name": "calculator", "tool_args": {"expression": "2 + 3"}, "answer": null}'
    parsed = parse_llm_response(raw)

    assert parsed.action == "tool_call"
    assert parsed.tool_name == "calculator"
    assert parsed.tool_args == {"expression": "2 + 3"}
    assert parsed.thought == "需要计算一下"
    assert parsed.parse_method == "direct"


def test_parse_final_answer_json():
    raw = '{"thought": "直接回答", "action": "final_answer", "tool_name": null, "tool_args": null, "answer": "北京是中国首都"}'
    parsed = parse_llm_response(raw)

    assert parsed.action == "final_answer"
    assert parsed.final_answer == "北京是中国首都"
    assert parsed.parse_method == "direct"


def test_parse_json_code_block():
    raw = """```json
{
  "thought": "需要搜索",
  "action": "tool_call",
  "tool_name": "search",
  "tool_args": {"query": "python 3.12"},
  "answer": null
}
```"""
    parsed = parse_llm_response(raw)

    assert parsed.action == "tool_call"
    assert parsed.tool_name == "search"
    assert parsed.parse_method == "code_block"


def test_parse_plain_code_block():
    """不带 json 标记的 ``` 代码块."""
    raw = """```
{"thought": "ok", "action": "final_answer", "tool_name": null, "tool_args": null, "answer": "hello"}
```"""
    parsed = parse_llm_response(raw)

    assert parsed.action == "final_answer"
    assert parsed.final_answer == "hello"


def test_parse_braces_fallback():
    raw = '好的，我来分析一下: {"thought": "ok", "action": "final_answer", "answer": "done"}'
    parsed = parse_llm_response(raw)

    assert parsed.action == "final_answer"


def test_parse_invalid_json_fallback():
    raw = "这不是 JSON 格式的内容 at all"
    parsed = parse_llm_response(raw)

    assert parsed.action == "final_answer"
    assert parsed.final_answer == raw
    assert parsed.parse_method == "fallback_text"


def test_parse_missing_tool_name_fallback():
    raw = '{"thought": "xxx", "action": "tool_call", "tool_name": null, "tool_args": {}, "answer": null}'
    parsed = parse_llm_response(raw)

    # 没有 tool_name 的 tool_call 应该降级
    assert parsed.action == "final_answer"


def test_parse_unknown_action():
    raw = '{"thought": "xxx", "action": "unknown_action", "answer": "oops"}'
    parsed = parse_llm_response(raw)

    # 未知 action → 兜底为 final_answer（有 answer）
    assert parsed.action == "final_answer"


def test_parse_tool_args_string_to_dict():
    """有些模型会把 tool_args 输出成 JSON 字符串."""
    raw = '{"thought": "ok", "action": "tool_call", "tool_name": "calculator", "tool_args": "{\\"expression\\":\\"1+2\\"}", "answer": null}'
    parsed = parse_llm_response(raw)

    assert parsed.action == "tool_call"
    assert parsed.tool_args == {"expression": "1+2"}


def test_parse_missing_action_field():
    """缺 action 但有 tool_name → 判为 tool_call."""
    raw = '{"thought": "ok", "tool_name": "calculator", "tool_args": {"expression": "1"}}'
    parsed = parse_llm_response(raw)

    assert parsed.action == "tool_call"
