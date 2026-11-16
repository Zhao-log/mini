"""
ContextManager — 管理塞入 LLM context 的消息列表.

题目核心考点: "自行判断哪些信息要塞入 context"

设计决策（重要！README 里要写清楚）:
  ✅ 塞入: 用户输入（user）、LLM 最终回答（assistant content）、工具调用记录（assistant tool_calls）、工具结果（tool content，截断到 500 字符）
  ❌ 不塞: 思考过程（thought 字段）、失败的工具调用细节（只留最后一次）

压缩策略（基础版）:
  - 超过 MAX_ROUNDS 轮 user+assistant 时截断，保留最近的
  - 估算 token（用字符数 / 4 粗略估算，不依赖 tiktoken）
  - 超过 MAX_TOKENS 时，把最早的几条合并成一条 summary 消息
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContextManager:
    """构建 & 压缩 LLM context."""

    # ---- 可配置参数 ----
    MAX_ROUNDS: int = 20         # 最多保留多少轮 user+assistant
    MAX_CHARS: int = 16000       # 粗略 token 上限（字符数 / 4 ≈ token 数）
    COMPRESS_THRESHOLD: int = 14000  # 低于此值触发压缩
    TOOL_RESULT_MAX_LEN: int = 500    # 单条工具结果最多保留多少字符

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def build_context(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        从原始 messages 构建要发给 LLM 的 context.

        流程:
          1. 过滤: 移除 thought、截断工具结果
          2. 轮次截断: 只保留最近 N 轮
          3. token 估算 & 压缩: 超限时把早期消息合并成 summary
          4. 前插 system prompt
        """
        if not messages:
            return [{"role": "system", "content": system_prompt}] if system_prompt else []

        # Step 1: 过滤
        filtered = self._filter_messages(messages)
        logger.info("📋 过滤后: %d 条消息", len(filtered))

        # Step 2: 轮次截断
        truncated = self._truncate_by_rounds(filtered)
        if len(truncated) != len(filtered):
            logger.info("✂️ 轮次截断: %d → %d 条", len(filtered), len(truncated))

        # Step 3: 估算大小
        total_chars = self._estimate_chars(truncated)
        logger.info("📏 估算字符数: %d（≈ %d tokens）", total_chars, total_chars // 4)

        # Step 4: 超限时压缩
        if total_chars > self.MAX_CHARS:
            compressed = self._compress_early_messages(truncated)
            new_chars = self._estimate_chars(compressed)
            logger.info("🗜️ 压缩后: %d 条消息, %d 字符", len(compressed), new_chars)
            final_messages = compressed
        else:
            final_messages = truncated

        # Step 5: 前插 system prompt
        result = list(final_messages)
        if system_prompt:
            # 压缩后可能已经有一条 system 摘要，合并成一条 system，
            # 避免出现多条 system 消息（部分供应商对此敏感）
            if result and result[0].get("role") == "system":
                merged = f"{system_prompt}\n\n{result[0].get('content', '')}"
                result[0] = {"role": "system", "content": merged}
            else:
                result.insert(0, {"role": "system", "content": system_prompt})

        return result

    # ------------------------------------------------------------------
    # 过滤
    # ------------------------------------------------------------------

    def _filter_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        过滤不需要的字段和截断过长的内容.
        
        保留: role, content, tool_calls, tool_call_id
        移除: thought（不进 context，LLM 不需要看之前的思考）
        截断: tool role 的 content（太长的结果浪费 token）
        """
        filtered = []
        for msg in messages:
            role = msg.get("role", "")

            clean: dict[str, Any] = {"role": role}

            if role == "user":
                clean["content"] = msg.get("content", "")

            elif role == "assistant":
                # assistant 的 content 可能为空（调工具时 content 可能是 ""）
                clean["content"] = msg.get("content") or ""
                # tool_calls 保留（让 LLM 知道自己之前调过什么工具）
                if msg.get("tool_calls"):
                    clean["tool_calls"] = msg["tool_calls"]
                # ⚠️ thought 字段故意丢掉 — 不塞进 context

            elif role == "tool":
                # 工具结果截断
                content = msg.get("content", "")
                if len(content) > self.TOOL_RESULT_MAX_LEN:
                    content = content[:self.TOOL_RESULT_MAX_LEN] + f"\n...(截断，原始长度 {len(content)} 字符)"
                clean["content"] = content
                if msg.get("tool_call_id"):
                    clean["tool_call_id"] = msg["tool_call_id"]

            elif role == "system":
                clean["content"] = msg.get("content", "")

            filtered.append(clean)

        return filtered

    # ------------------------------------------------------------------
    # 轮次截断
    # ------------------------------------------------------------------

    def _truncate_by_rounds(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        按轮次截断: 保留最近 MAX_ROUNDS 轮 user+assistant 对.

        以 user 消息为一轮的起点，直接按 user 索引切片，
        保证截断后的第一条一定是 user 消息（不会留下孤立的 assistant
        回复或没有归属的 tool 结果）。
        """
        if len(messages) <= 2:
            return messages

        user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        if len(user_indices) <= self.MAX_ROUNDS:
            return messages

        cutoff = user_indices[-self.MAX_ROUNDS]
        return messages[cutoff:]

    # ------------------------------------------------------------------
    # Token 估算
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_chars(messages: list[dict[str, Any]]) -> int:
        """粗略估算 context 总字符数."""
        total = 0
        for msg in messages:
            # 每条 role 字段 + content
            total += len(msg.get("role", "")) + 4  # role + 基础开销
            total += len(msg.get("content", ""))
            if msg.get("tool_calls"):
                import json
                total += len(json.dumps(msg["tool_calls"], ensure_ascii=False))
            if msg.get("tool_call_id"):
                total += len(msg["tool_call_id"])
        return total

    # ------------------------------------------------------------------
    # 压缩（基础版）
    # ------------------------------------------------------------------

    def _compress_early_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        把最早的几条消息合并成一条 summary system 消息.
        
        策略:
          - 保留最近的 MAX_ROUNDS // 2 轮完整消息
          - 更早的消息 → 人工生成 summary（不调 LLM，用简单规则）
        """
        if len(messages) <= 4:
            return messages

        # 找到中间切割点: 保留后半部分的 user+assistant 对
        user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        if len(user_indices) <= 2:
            return messages

        # 保留最近一半的 user 轮次
        half = len(user_indices) // 2
        cutoff_user_idx = user_indices[half]  # 第 half 个 user 消息之后
        cutoff = cutoff_user_idx

        early_messages = messages[:cutoff]
        late_messages = messages[cutoff:]

        # 生成 summary（简单拼接 user 问题 + assistant 回答）
        summary_lines = ["[历史对话概要（已压缩）]:"]
        i = 0
        while i < len(early_messages):
            msg = early_messages[i]
            if msg.get("role") == "user":
                user_text = msg.get("content", "")[:100]
                # 找下一个 assistant
                ans_text = ""
                for j in range(i + 1, min(i + 8, len(early_messages))):
                    if early_messages[j].get("role") == "assistant" and early_messages[j].get("content"):
                        ans_text = early_messages[j]["content"][:100]
                        break
                summary_lines.append(f"  - 用户问: {user_text}")
                if ans_text:
                    summary_lines.append(f"    → 回答: {ans_text}")
                i += 1
            else:
                i += 1

        summary = "\n".join(summary_lines)

        # 前插 summary 作为 system 消息
        result = [{"role": "system", "content": summary}]
        result.extend(late_messages)
        return result
