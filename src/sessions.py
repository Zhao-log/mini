"""
Session & SessionManager — 多窗口隔离的对话状态管理.

设计决策:
  - Session 封装一个独立的对话上下文 + trace
  - SessionManager 用内存 dict 管理，按 session_id 隔离
  - 每个 Session 有独立的 messages 和 trace
  - 简单可靠，满足题目"窗口1/窗口2独立 session"的要求
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """单个 session 的状态."""
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def created_at_str(self) -> str:
        return datetime.fromtimestamp(self.created_at).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def updated_at_str(self) -> str:
        return datetime.fromtimestamp(self.updated_at).strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------------

    def add_message(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)
        self.updated_at = time.time()
        logger.debug("📥 [%s] +message: role=%s", self.session_id, msg.get("role"))

    def add_trace(self, entry: str) -> None:
        self.trace.append(entry)
        self.updated_at = time.time()
        logger.debug("📝 [%s] +trace: %s", self.session_id, entry[:80])

    def get_messages(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def get_trace_text(self) -> str:
        return "\n".join(self.trace)

    def message_count(self) -> int:
        return len(self.messages)

    def user_assistant_turns(self) -> int:
        """统计有多少轮 user+assistant 对（粗略）."""
        count = 0
        for msg in self.messages:
            if msg.get("role") == "assistant" and msg.get("content"):
                count += 1
        return count

    def reset(self) -> None:
        """清空对话历史但保留 trace."""
        self.messages.clear()
        self.updated_at = time.time()
        self.add_trace("🔄 Session 已重置")


class SessionManager:
    """Session 注册中心."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            logger.info("🆕 创建新 session: %s", session_id)
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("🗑️ 删除 session: %s", session_id)
            return True
        return False

    def list_sessions(self) -> list[str]:
        return sorted(self._sessions.keys())

    def session_info(self) -> list[dict[str, Any]]:
        """返回每个 session 的概览信息（CLI 展示用）."""
        return [
            {
                "id": s.session_id,
                "messages": s.message_count(),
                "turns": s.user_assistant_turns(),
                "created": s.created_at_str,
                "updated": s.updated_at_str,
            }
            for s in self._sessions.values()
        ]
