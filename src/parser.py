"""
Parser — 从 LLM 输出文本中提取结构化 JSON 并解析。

容错策略（按优先级降级）:
  1. 直接 json.loads
  2. 从 ```json ... ``` 代码块里提取再解析
  3. 从 { ... } 大括号里提取最可能的 JSON 片段
  4. 全部失败 → 把整个输出当 final_answer（兜底）
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class ParsedResponse:
    """LLM 输出的结构化解析结果."""
    thought: str | None                           # 思考过程
    action: Literal["tool_call", "final_answer"]  # 动作类型
    tool_name: str | None                         # 工具名（action=tool_call 时）
    tool_args: dict[str, Any] | None              # 工具参数
    final_answer: str | None                      # 最终回答（action=final_answer 时）
    raw_json: dict[str, Any] | None = None        # 原始 JSON（调试用）
    parse_method: str = ""                        # 用的哪种解析策略（调试用）


def _extract_json_code_block(text: str) -> str | None:
    """从 ```json ... ``` 或 ``` ... ``` 中提取."""
    # ```json\n...\n```
    m = re.search(r"```(?:json)?\s*\n(.*?)\n?\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _extract_json_braces(text: str) -> str | None:
    """从文本中找到最外层 { ... } 包裹的内容."""
    # 找第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        # 验证是不是合法 JSON
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
    return None


def parse_llm_response(raw_text: str) -> ParsedResponse:
    """
    解析 LLM 输出为 ParsedResponse.
    
    :param raw_text: LLM 返回的原始文本（期望是 JSON 格式）
    :return: ParsedResponse
    """
    text = raw_text.strip()
    logger.debug("📝 原始 LLM 输出:\n%s", text[:500])

    # 尝试不同的提取策略
    json_str = None
    method = ""

    # 策略 1: 直接 json.loads
    try:
        data = json.loads(text)
        json_str = text
        method = "direct"
    except json.JSONDecodeError:
        pass

    # 策略 2: 从代码块提取
    if json_str is None:
        extracted = _extract_json_code_block(text)
        if extracted:
            try:
                data = json.loads(extracted)
                json_str = extracted
                method = "code_block"
            except json.JSONDecodeError:
                pass

    # 策略 3: 从大括号提取
    if json_str is None:
        extracted = _extract_json_braces(text)
        if extracted:
            try:
                data = json.loads(extracted)
                json_str = extracted
                method = "braces"
            except json.JSONDecodeError:
                pass

    # 策略 4: 全部失败 → 降级为 final_answer
    if json_str is None:
        logger.warning("⚠️ LLM 输出无法解析为 JSON，降级为 final_answer")
        return ParsedResponse(
            thought=None,
            action="final_answer",
            tool_name=None,
            tool_args=None,
            final_answer=text,
            raw_json=None,
            parse_method="fallback_text",
        )

    method = method or "unknown"

    # 兼容 list（理论上不应该，但有些模型会输出数组）
    if isinstance(data, list) and len(data) == 1:
        data = data[0]

    if not isinstance(data, dict):
        logger.warning("⚠️ JSON 顶层不是 dict，降级为 final_answer")
        return ParsedResponse(
            thought=None,
            action="final_answer",
            tool_name=None,
            tool_args=None,
            final_answer=str(data),
            raw_json=None,
            parse_method="fallback_non_dict",
        )

    # 提取字段
    thought = data.get("thought") or data.get("reasoning")
    action = data.get("action", "")
    tool_name = data.get("tool_name")
    tool_args = data.get("tool_args")
    final_answer = data.get("answer") or data.get("final_answer")

    # 校验 action
    if action not in ("tool_call", "final_answer"):
        # 兜底: 有 tool_name 就当 tool_call，否则 final_answer
        if tool_name:
            action = "tool_call"
        else:
            action = "final_answer"

    # 进一步校验
    if action == "tool_call":
        if not tool_name:
            logger.warning("⚠️ action=tool_call 但 tool_name 缺失，降级为 final_answer")
            action = "final_answer"
            final_answer = final_answer or f"(模型输出了 tool_call 但缺少工具名)\n{json.dumps(data, ensure_ascii=False)}"
        # tool_args 确保是 dict
        if tool_args is None:
            tool_args = {}
        elif isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except json.JSONDecodeError:
                tool_args = {"_raw": tool_args}

    if action == "final_answer" and not final_answer:
        final_answer = data.get("answer") or "(模型未给出最终答案)"

    logger.info(
        "✅ 解析完成 [%s]: action=%s tool=%s",
        method, action, tool_name if action == "tool_call" else "-"
    )

    return ParsedResponse(
        thought=thought,
        action=action,
        tool_name=tool_name,
        tool_args=tool_args if isinstance(tool_args, dict) else {},
        final_answer=final_answer,
        raw_json=data,
        parse_method=method,
    )
