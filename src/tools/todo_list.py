"""
TodoList — 待办事项管理工具。

第三个自定义工具，体现跨 session 的独立状态管理能力。
设计: 内部用一个 dict 存每个 session 的待办列表，不依赖外部存储。
"""

from __future__ import annotations

import threading
from typing import Any

from . import Tool, CURRENT_SESSION_ID


# 全局状态: {session_id: [{"id": int, "item": str, "done": bool}]}
_state: dict[str, list[dict[str, Any]]] = {}
_lock = threading.Lock()  # 线程安全（demo 够用）


def _ensure_session(session_id: str) -> list[dict[str, Any]]:
    with _lock:
        if session_id not in _state:
            _state[session_id] = []
        return _state[session_id]


def _todos_to_text(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return "(空)"
    lines = []
    for t in todos:
        marker = "✅" if t["done"] else "⬜"
        lines.append(f"  [{t['id']}] {marker} {t['item']}")
    return "\n".join(lines)


def todo_handler(action: str, item: str | None = None, session_id: str | None = None) -> str:
    """
    待办事项 handler.

    :param action: add | remove | list | complete
    :param item:  add 时是待办内容，remove/complete 时可以是 ID 或内容关键词
    :param session_id: 一般不需要 LLM 传；由 ToolRegistry 通过 contextvar 注入，
                       实现不同会话的待办互相隔离
    """
    # 优先级: 显式传入 > 运行时注入 > 兜底全局
    effective_session = session_id or CURRENT_SESSION_ID.get() or "_global"
    todos = _ensure_session(effective_session)

    if action == "list":
        return f"📋 当前待办:\n{_todos_to_text(todos)}"

    if action == "add":
        if not item:
            raise ValueError("add 操作需要提供 item 参数")
        with _lock:
            new_id = max((t["id"] for t in todos), default=0) + 1
            todos.append({"id": new_id, "item": item.strip(), "done": False})
        return f"✅ 已添加: {item.strip()}\n📋 当前待办:\n{_todos_to_text(todos)}"

    if action == "complete":
        if not item:
            raise ValueError("complete 操作需要提供 item 参数（ID 或关键词）")
        with _lock:
            target_id = int(item) if str(item).isdigit() else None
            found = None
            for t in todos:
                if target_id is not None and t["id"] == target_id:
                    found = t
                    break
                if item.lower() in t["item"].lower():
                    found = t
                    break
            if not found:
                return f"❌ 未找到匹配的待办: {item}\n📋 当前待办:\n{_todos_to_text(todos)}"
            found["done"] = True
        return f"🎉 已完成 [{found['id']}]: {found['item']}\n📋 当前待办:\n{_todos_to_text(todos)}"

    if action == "remove":
        if not item:
            raise ValueError("remove 操作需要提供 item 参数（ID 或关键词）")
        with _lock:
            target_id = int(item) if str(item).isdigit() else None
            removed = None
            for i, t in enumerate(todos):
                if target_id is not None and t["id"] == target_id:
                    removed = todos.pop(i)
                    break
                if item.lower() in t["item"].lower():
                    removed = todos.pop(i)
                    break
            if not removed:
                return f"❌ 未找到匹配的待办: {item}"
        return f"🗑️ 已删除 [{removed['id']}]: {removed['item']}\n📋 当前待办:\n{_todos_to_text(todos)}"

    raise ValueError(f"未知操作: {action}（支持: add, remove, list, complete）")


TODO_TOOL = Tool(
    name="todo_list",
    description=(
        "待办事项管理工具，支持添加(add)、删除(remove)、列出(list)、标记完成(complete)。"
        "add 需要 item 参数；remove/complete 的 item 可以是待办 ID 或内容关键词。"
        "list 不需要任何参数。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "list", "complete"],
                "description": "要执行的操作类型",
            },
            "item": {
                "type": "string",
                "description": "待办内容（add 时必填）或 ID/关键词（remove/complete 时用）。list 时不需要。",
            },
        },
        "required": ["action"],
    },
    handler=todo_handler,
)
