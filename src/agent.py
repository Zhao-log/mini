"""
Agent — 核心 ReAct 循环.

这是整个题目的心脏。不能依赖任何现有 Agent 框架的主流程。

Loop 四步 (对题目要求2的直接实现):
  Step 1: 接收用户输入
  Step 2: 判断是直接回复还是调用工具（LLM 决策）
  Step 3: 调用工具（如果需要）
  Step 4: 根据工具结果判断继续 loop 还是返回（回到 Step 2）

设计决策:
  - 用 LLM response_format=json_object 强制输出规范 JSON
  - 手写 parser 从 JSON 里提取 action / tool_call / answer
  - Session 隔离由 SessionManager 管，Agent 通过 session_id 路由
  - Context 管理（过滤、截断、压缩）由 ContextManager 管
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .exceptions import AgentError, ToolExecutionError, ToolNotFoundError
from .llm_client import LLMClient
from .memory import ContextManager
from .parser import ParsedResponse, parse_llm_response
from .sessions import SessionManager
from .tools import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Prompt 模板
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """你是一个智能 Agent，可以理解用户问题并自主决定是否使用工具。

## 可用工具
{tools_description}

## 输出格式（严格遵守，只输出 JSON）
你必须且只能输出一个 JSON 对象，格式如下:
```json
{{
  "thought": "你的思考过程（可以用中文，分析用户意图、判断是否需要工具）",
  "action": "tool_call" 或 "final_answer",
  "tool_name": "工具名称（仅当 action=tool_call 时必填）",
  "tool_args": {{"key": "value"}}（仅当 action=tool_call 时必填，值类型要符合工具参数要求）,
  "answer": "最终回答文本（仅当 action=final_answer 时必填）"
}}
```

## 决策规则
1. 如果用户问题可以直接回答（事实性、简单计算、概念解释）→ action="final_answer"
2. 如果需要查信息、搜索、计算、操作待办 → action="tool_call"，选最合适的工具
3. 工具执行完后，根据结果给出 final_answer（不要再次调用相同工具）
4. 如果之前调用工具失败，可以在 thought 里分析原因后换个参数重试
5. 工具参数必须符合 Schema 要求的类型（string/number/boolean/object/array）
6. 不要在 JSON 里写注释，不要输出 JSON 以外的任何内容（包括 ```json 代码块标记）
"""


# ---------------------------------------------------------------------------
# Agent 类
# ---------------------------------------------------------------------------

class Agent:
    """
    最小可用 Agent.
    
    核心循环: 用户输入 → LLM 决策 → 工具调用 / 直接回答 → 循环或结束
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        session_manager: SessionManager | None = None,
        context_manager: ContextManager | None = None,
        max_steps: int = 10,
        system_prompt_template: str | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.session_manager = session_manager or SessionManager()
        self.context_manager = context_manager or ContextManager()
        self.max_steps = max_steps
        self.system_prompt_template = system_prompt_template or SYSTEM_PROMPT_TEMPLATE

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def chat(self, session_id: str, user_input: str) -> str:
        """
        与 Agent 对话.
        
        :param session_id: 会话 ID（不同 session_id 隔离上下文）
        :param user_input: 用户输入
        :return: Agent 的最终回答
        """
        session = self.session_manager.get_or_create(session_id)

        # Step 1: 接收用户输入
        session.add_message({"role": "user", "content": user_input})
        session.add_trace(f"👤 用户输入: {user_input}")

        # 构建 system prompt（包含工具描述）
        system_prompt = self.system_prompt_template.format(
            tools_description=self.tools.get_tools_description_text()
        )

        # ReAct 循环
        start_time = time.time()
        for step in range(self.max_steps):
            step_num = step + 1
            session.add_trace(f"\n{'='*50}")
            session.add_trace(f"📦 Step {step_num}/{self.max_steps}")

            # Step 2: 构建 context + 调 LLM（判断直接回复还是调工具）
            context = self.context_manager.build_context(
                session.get_messages(),
                system_prompt=None,   # system prompt 单独传给 llm.chat
            )
            session.add_trace(
                f"📏 Context 大小: {len(context)} 条消息, "
                f"估算 {self.context_manager._estimate_chars(context)} 字符"
            )

            try:
                llm_response = self.llm.chat(
                    messages=context,
                    tools=self.tools.get_all_tools_schema(),
                    system_prompt=system_prompt,
                )
            except Exception as e:
                # LLM API 调用失败 → 返回错误
                error_msg = f"❌ LLM 调用失败: {e}"
                session.add_trace(error_msg)
                # 把错误信息也存进 context，让 LLM 有机会在下一轮恢复（虽然大概率到此为止）
                session.add_message({"role": "assistant", "content": error_msg})
                return error_msg

            # 解析 LLM 输出
            parsed = parse_llm_response(llm_response.content)

            # 记录思考过程（进 trace，不进 context）
            if parsed.thought:
                session.add_trace(f"💭 Thought: {parsed.thought}")

            session.add_trace(
                f"🎯 决策: action={parsed.action}, "
                f"tool={parsed.tool_name or '-'}"
            )

            # Step 4: 判断分支
            if parsed.action == "final_answer":
                # ── 直接回答 ──
                answer = parsed.final_answer or "(模型未给出答案)"
                session.add_message({"role": "assistant", "content": answer})
                session.add_trace(f"✅ Final Answer: {answer}")
                elapsed = time.time() - start_time
                session.add_trace(f"⏱️ 耗时: {elapsed:.1f}s, 共 {step_num} 步")
                return answer

            if parsed.action == "tool_call":
                # ── 工具调用 ──
                tool_name = parsed.tool_name or ""
                tool_args = parsed.tool_args or {}

                # 先把 LLM 的 tool_call 意图存入 session
                # 注意: content 留空，思考过程只进 trace 不进 context
                # （避免把 thought 当作 assistant 正文污染后续上下文）
                session.add_message({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "name": tool_name,
                        "arguments": tool_args,
                        "id": f"call_{session_id}_{step}",
                    }],
                })

                # Step 3: 执行工具
                try:
                    tool_result = self.tools.execute(tool_name, tool_args, session_id=session_id)
                except ToolNotFoundError as e:
                    tool_result = f"❌ {e}"
                except ToolExecutionError as e:
                    tool_result = f"❌ {e}"
                except Exception as e:
                    tool_result = f"❌ 未知错误: {e}"

                # 记录 trace
                tool_result_display = tool_result[:300] + ("..." if len(tool_result) > 300 else "")
                session.add_trace(
                    f"🔧 Tool call: {tool_name}({tool_args}) → {tool_result_display}"
                )

                # 工具结果存入 session → 下一轮循环时会自动进 context
                session.add_message({
                    "role": "tool",
                    "tool_call_id": f"call_{session_id}_{step}",
                    "content": tool_result,
                })

                # 循环继续 → 回到 Step 2，LLM 看到工具结果后会做新的决策
                continue

            # 理论上不会到这里（parse_llm_response 已经兜底了）
            # 但万一的兜底
            fallback = f"⚠️ 无法解析 LLM 决策，原始输出: {llm_response.content[:500]}"
            session.add_message({"role": "assistant", "content": fallback})
            session.add_trace(fallback)
            return fallback

        # ── 超过最大步数 ──
        elapsed = time.time() - start_time
        overflow_msg = (
            f"⚠️ 达到最大步数限制 ({self.max_steps} 步)，Agent 未在限制内完成。\n"
            f"已进行的步骤可以在 trace 中查看。"
        )
        # 与其它返回路径保持一致: 最终回答必须落进 messages，
        # 否则 Web/CLI 下一次读取 session 时这轮回答会凭空消失。
        session.add_message({"role": "assistant", "content": overflow_msg})
        session.add_trace(f"⏱️ 超时: {elapsed:.1f}s, {self.max_steps} 步耗尽")
        return overflow_msg

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def get_trace(self, session_id: str) -> str:
        """获取某个 session 的完整 trace."""
        session = self.session_manager.get(session_id)
        if not session:
            return f"Session '{session_id}' 不存在"
        return session.get_trace_text()

    def get_sessions(self) -> list[dict[str, Any]]:
        return self.session_manager.session_info()

    def reset_session(self, session_id: str) -> bool:
        session = self.session_manager.get(session_id)
        if session:
            session.reset()
            return True
        return False
