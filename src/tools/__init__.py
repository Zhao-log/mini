"""
Tool 系统 — 注册机制 + JSON Schema 驱动 + 执行分发。

设计决策:
  - 每个 Tool 有 name / description / parameters(JSON Schema) / handler
  - ToolRegistry 统一管理，暴露给 LLM 的就是 get_all_tools_schema()
  - handler 签名统一: (**kwargs) -> str，返回工具执行结果的字符串
"""

from __future__ import annotations

import contextvars
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from ..exceptions import ToolExecutionError, ToolNotFoundError

logger = logging.getLogger(__name__)


# 当前正在执行的 session_id —— 由 ToolRegistry.execute 注入，
# 工具 handler 可通过 CURRENT_SESSION_ID.get() 读取，实现按会话隔离状态，
# 而不需要把 session_id 暴露到 JSON Schema 里让 LLM 去填（LLM 也不该知道）。
CURRENT_SESSION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)


@dataclass
class Tool:
    """单个工具的定义."""
    name: str
    description: str
    parameters: dict[str, Any]                       # JSON Schema
    handler: Callable[..., Any]                      # 实际执行函数

    def to_schema(self) -> dict[str, Any]:
        """转成 OpenAI tools 列表里的一项."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, **kwargs: Any) -> str:
        """执行工具，捕获异常并返回错误字符串."""
        try:
            result = self.handler(**kwargs)
            return str(result)
        except TypeError as e:
            # 参数不匹配
            sig = inspect.signature(self.handler)
            raise ToolExecutionError(f"参数错误: {e}. 期望签名: {sig}") from e
        except Exception as e:
            raise ToolExecutionError(f"{self.name} 执行失败: {e}") from e


class ToolRegistry:
    """工具注册中心."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------------
    # 管理
    # ------------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning("工具 '%s' 已存在，将被覆盖", tool.name)
        self._tools[tool.name] = tool
        logger.info("✓ 注册工具: %s", tool.name)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # 给 LLM 用的接口
    # ------------------------------------------------------------------

    def get_all_tools_schema(self) -> list[dict[str, Any]]:
        """返回给 LLM 的 tools 参数列表（OpenAI 格式）."""
        return [t.to_schema() for t in self._tools.values()]

    def get_tools_description_text(self) -> str:
        """纯文本的工具描述（给 system prompt 用，当不用 tools 参数时兜底）."""
        lines = []
        for t in self._tools.values():
            params_desc = ""
            props = t.parameters.get("properties", {})
            required = t.parameters.get("required", [])
            for pname, pschema in props.items():
                marker = "(必填)" if pname in required else "(可选)"
                pdesc = pschema.get("description", "")
                ptype = pschema.get("type", "any")
                params_desc += f"      - {pname} {marker}: {ptype}, {pdesc}\n"
            lines.append(f"  - {t.name}: {t.description}\n    参数:\n{params_desc.rstrip()}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def execute(self, name: str, args: dict[str, Any], session_id: str | None = None) -> str:
        """
        根据名称执行工具。

        :param name: 工具名
        :param args: 工具参数（来自 LLM）
        :param session_id: 调用方会话 ID，会被注入到 CURRENT_SESSION_ID，
                           供需要按会话隔离状态的工具（如 todo_list）读取
        """
        if name not in self._tools:
            available = ", ".join(self._tools.keys()) or "(无可用工具)"
            raise ToolNotFoundError(f"工具 '{name}' 不存在。可用工具: {available}")

        tool = self._tools[name]
        logger.info("🔧 执行工具: %s(%s)", name, args)

        token = CURRENT_SESSION_ID.set(session_id)
        try:
            result = tool.execute(**args)
        finally:
            CURRENT_SESSION_ID.reset(token)

        logger.info("🔧 工具返回: %s", result[:200])
        return result
