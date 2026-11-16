"""
main.py — 交互式 CLI 入口.

运行: python main.py
命令:
  /session <id>  切换或创建 session
  /sessions      列出所有 session
  /trace         查看当前 session 的执行 trace
  /reset         清空当前 session
  /quit /exit    退出

多窗口演示: 开两个终端，不同的 session_id 互不影响.
"""

from __future__ import annotations

import logging
import os
import sys

# 让 src 能被 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()  # 自动加载 .env

from src.agent import Agent
from src.llm_client import LLMClient
from src.sessions import SessionManager
from src.tools import ToolRegistry
from src.tools.calculator import CALCULATOR_TOOL
from src.tools.search import SEARCH_TOOL
from src.tools.todo_list import TODO_TOOL


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx 太吵了
    logging.getLogger("httpx").setLevel(logging.WARNING)


def setup_console_encoding() -> None:
    """
    兼容中文 Windows 控制台。

    cmd.exe 默认代码页是 936(GBK)，无法编码 emoji，直接 print 会抛
    UnicodeEncodeError 导致程序崩溃。这里保留控制台原有编码（保证中文正常），
    只把错误策略改成 replace，让无法编码的字符降级为 '?'。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def build_agent() -> Agent:
    """组装一个完整的 Agent."""
    llm = LLMClient()

    registry = ToolRegistry()
    registry.register(CALCULATOR_TOOL)
    registry.register(SEARCH_TOOL)
    registry.register(TODO_TOOL)

    session_manager = SessionManager()

    return Agent(
        llm=llm,
        tools=registry,
        session_manager=session_manager,
        max_steps=10,
    )


def print_help() -> None:
    print(
        """
可用命令:
  /session <id>   切换或创建一个新 session
  /sessions       列出所有 session（含消息数）
  /trace          查看当前 session 的执行 trace
  /reset          清空当前 session 的对话历史
  /tools          列出当前注册的工具
  /help           显示此帮助
  /quit /exit     退出

直接输入问题开始对话。两个终端用不同 session_id 互不影响。
"""
    )


def main() -> None:
    setup_console_encoding()
    setup_logging()

    # 检查 API Key
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key or api_key.startswith("sk-your"):
        print("⚠️  未检测到有效的 LLM_API_KEY！")
        print("   请复制 .env.example 为 .env 并填入真实 API Key。")
        print("   程序仍会启动，但调用 LLM 时会失败。\n")

    print("🤖 Minimal Agent — 从零实现的最小可用 Agent")
    print("=" * 50)

    agent = build_agent()
    current_session = "default"

    print(f"✅ 已注册工具: {agent.tools.list_tools()}")
    print(f"🆔 当前 session: {current_session}")
    print_help()

    # 主循环
    while True:
        try:
            prompt = f"[{current_session}] > "
            user_input = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue

        # 命令处理
        if user_input.startswith("/"):
            cmd = user_input[1:].lower()
            parts = cmd.split(maxsplit=1)
            cmd_name = parts[0]
            cmd_arg = parts[1] if len(parts) > 1 else ""

            if cmd_name in ("quit", "exit", "q"):
                print("👋 再见！")
                break

            elif cmd_name == "help":
                print_help()

            elif cmd_name == "session":
                sid = cmd_arg.strip() or "default"
                current_session = sid
                agent.session_manager.get_or_create(sid)
                print(f"✅ 切换到 session: {sid}")

            elif cmd_name == "sessions":
                info = agent.get_sessions()
                if not info:
                    print("(暂无 session)")
                else:
                    print(f"{'ID':<20} {'消息':>6} {'轮次':>6} {'最后更新':>20}")
                    print("-" * 54)
                    for s in info:
                        print(
                            f"{s['id']:<20} {s['messages']:>6} {s['turns']:>6} {s['updated']:>20}"
                        )

            elif cmd_name == "trace":
                trace_text = agent.get_trace(current_session)
                print(f"─── trace for [{current_session}] ───")
                print(trace_text if trace_text else "(暂无 trace)")
                print("─── end trace ───")

            elif cmd_name == "reset":
                agent.reset_session(current_session)
                print(f"🔄 已重置 session: {current_session}")

            elif cmd_name == "tools":
                print(f"当前可用工具:")
                for name in agent.tools.list_tools():
                    print(f"  • {name}")

            else:
                print(f"❓ 未知命令: /{cmd_name}（输入 /help 查看帮助）")

            continue

        # 正常对话
        print("🤔 thinking...", end="", flush=True)
        try:
            answer = agent.chat(current_session, user_input)
        except Exception as e:
            print(f"\n❌ 运行异常: {e}")
            logging.exception("Agent chat 出错")
            continue

        # 覆盖 thinking...
        print("\r" + " " * 14 + "\r", end="", flush=True)
        print(f"🤖: {answer}")
        print()


if __name__ == "__main__":
    main()
