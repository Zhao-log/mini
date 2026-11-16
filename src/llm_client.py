"""
LLM Client — 手写 HTTP 调用，不依赖任何 LLM SDK。

设计决策:
  - 直接发 JSON 到 OpenAI Chat Completions endpoint
  - 不让 SDK 帮我做 tool_call 解析或 function calling 的自动处理
  - 用 response_format: json_object 强制模型输出 JSON（不支持时自动降级重试）
  - 返回结构化的 LLMResponse，让上层 parser 自己处理
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """
    LLM 返回的结构化响应。

    注意: content 就是模型输出的原始文本（应该是 JSON 字符串），
    上层 parser 负责把它解析成 ParsedResponse。
    """
    content: str
    raw: dict = field(default_factory=dict)    # 原始 API 响应（调试用）
    usage: dict | None = None                   # token 用量


class LLMClient:
    """
    手写 HTTP 的 LLM 客户端。
    兼容 OpenAI 格式的 endpoint（OpenAI / DeepSeek / DashScope / 本地模型 等）。
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self.timeout = timeout

        if not self.api_key:
            logger.warning("LLM_API_KEY 未设置，调用可能会失败。请在 .env 文件中配置。")

    # ------------------------------------------------------------------
    # 核心方法
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        调用 LLM Chat Completions。

        :param messages: 对话历史（不含 system，system 单独传）
        :param tools: 可选的工具定义列表（JSON Schema 格式）
        :param system_prompt: 系统提示词
        :param temperature: 采样温度
        :return: LLMResponse
        """
        url = f"{self.base_url}/chat/completions"

        # 组装消息
        api_messages: list[dict[str, Any]] = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(self._normalize_messages(messages))

        # 组装请求体 —— 强制 JSON 输出
        body: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},   # ⭐ 强制输出 JSON
        }

        # 如果有工具，把 tools 也塞进去（OpenAI 格式）
        # 但注意: 我们不用 SDK 的自动 tool_call 解析，所有解析由上层 parser 完成
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.debug("→ POST %s | messages=%d tools=%s", url, len(api_messages), bool(tools))

        data = self._post(url, headers, body)

        # 提取 content
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM 响应缺少 choices 字段: {json.dumps(data, ensure_ascii=False)[:500]}")

        message = choices[0].get("message", {}) or {}
        content = self._coerce_content(message)

        return LLMResponse(
            content=content,
            raw=data,
            usage=data.get("usage"),
        )

    # ------------------------------------------------------------------
    # HTTP 层（含供应商兼容降级）
    # ------------------------------------------------------------------

    def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        """
        发送请求并返回 JSON。

        兼容性处理: 部分供应商（本地模型、部分兼容网关）不支持
        response_format=json_object，会返回 400。此时去掉该字段重试一次。
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=headers, json=body)

                if resp.status_code >= 400:
                    text = resp.text
                    logger.error("LLM API error: %s\n%s", resp.status_code, text)

                    if (
                        resp.status_code == 400
                        and "response_format" in body
                        and "response_format" in text
                    ):
                        logger.warning("供应商不支持 response_format，降级去掉该字段后重试一次")
                        fallback = {k: v for k, v in body.items() if k != "response_format"}
                        resp = client.post(url, headers=headers, json=fallback)
                        if resp.status_code >= 400:
                            logger.error("降级重试仍失败: %s\n%s", resp.status_code, resp.text)
                            raise RuntimeError(
                                f"LLM API 返回 {resp.status_code}: {resp.text}"
                            )
                        return resp.json()

                    raise RuntimeError(f"LLM API 返回 {resp.status_code}: {text}")

                return resp.json()

        except httpx.RequestError as e:
            logger.error("LLM API 请求失败: %s", e)
            raise RuntimeError(f"LLM API 请求失败: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("LLM 响应不是合法 JSON: %s", e)
            raise RuntimeError(f"LLM 响应不是合法 JSON: {e}") from e

    # ------------------------------------------------------------------
    # 响应内容归一化
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_content(message: dict[str, Any]) -> str:
        """
        把模型响应归一化成 JSON 字符串（我们自己的协议）。

        覆盖多种供应商差异:
          - content 是字符串（标准情况）
          - content 为 None + 原生 tool_calls（function calling 模式）
          - content 为 None + 空响应
          - content 是 list（多模态 content parts）
        """
        content = message.get("content")

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            content = "".join(parts) or None

        if isinstance(content, str) and content.strip():
            return content

        # content 为空 → 看原生 tool_calls
        tool_calls_raw = message.get("tool_calls") or []
        if tool_calls_raw:
            first = tool_calls_raw[0]
            fn = first.get("function", {}) if isinstance(first, dict) else {}
            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    parsed_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    parsed_args = {"_raw": raw_args}
            elif isinstance(raw_args, dict):
                parsed_args = raw_args
            else:
                parsed_args = {}

            return json.dumps(
                {
                    "thought": message.get("reasoning_content") or "模型调用了工具",
                    "action": "tool_call",
                    "tool_name": fn.get("name"),
                    "tool_args": parsed_args,
                    "answer": None,
                },
                ensure_ascii=False,
            )

        # 完全空响应
        return json.dumps(
            {
                "thought": message.get("reasoning_content") or "",
                "action": "final_answer",
                "tool_name": None,
                "tool_args": None,
                "answer": "(模型返回为空)",
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # 消息格式转换
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        把我们内部的 message 格式转成 OpenAI API 能接受的格式。

        内部格式（session 里存的）可能有 thought / trace 等额外字段，
        发 API 时需要去掉，只保留 role / content / tool_calls / tool_call_id。

        ⭐ 关键: assistant 的 tool_calls 必须转换成 OpenAI 线上格式
            {"id", "type": "function", "function": {"name", "arguments": <JSON 字符串>}}
        否则真实服务端会返回 400（arguments 必须是字符串，type 必填）。
        """
        normalized: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")

            if role == "tool":
                normalized.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": str(msg.get("content", "")),
                })
                continue

            if role == "assistant":
                clean: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                }
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    clean["tool_calls"] = [
                        LLMClient._to_openai_tool_call(tc) for tc in tool_calls
                    ]
                normalized.append(clean)
                continue

            normalized.append({"role": role, "content": str(msg.get("content", ""))})

        return normalized

    @staticmethod
    def _to_openai_tool_call(tc: dict[str, Any]) -> dict[str, Any]:
        """
        单个 tool_call 转 OpenAI 线上格式。

        同时兼容两种输入:
          - 内部简化格式 {"name": ..., "arguments": {...}, "id": ...}
          - 已是 OpenAI 原生格式 {"id","type","function":{"name","arguments"}}
        """
        call_id = tc.get("id") or f"call_{uuid4().hex[:12]}"

        fn = tc.get("function")
        if isinstance(fn, dict):
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
        else:
            name = tc.get("name", "")
            raw_args = tc.get("arguments", {})

        if isinstance(raw_args, str):
            arguments = raw_args
        else:
            arguments = json.dumps(raw_args if raw_args is not None else {}, ensure_ascii=False)

        return {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        }
