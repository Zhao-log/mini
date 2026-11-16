"""
Minimal Agent Web 入口。

使用 Python 标准库提供静态页面与同源 JSON API，不引入 Web 框架。
运行: python web_server.py
默认地址: http://127.0.0.1:8080

设计边界:
  - Agent / SessionManager / ToolRegistry 仍由 src/ 中的核心实现提供。
  - 本文件只负责 HTTP 协议、参数校验与数据序列化，不复制 ReAct 逻辑。
  - 默认仅监听本机回环地址；会话保存在内存中，重启后清空。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from src.agent import Agent
from src.sessions import Session

logger = logging.getLogger(__name__)

WEB_ROOT = Path(__file__).resolve().parent / "web"
MAX_REQUEST_BYTES = 32 * 1024
MAX_MESSAGE_CHARS = 4000
SESSION_ID_PATTERN = re.compile(r"^[\w][\w .-]{0,63}$", re.UNICODE)

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/api.js": ("api.js", "text/javascript; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class APIError(Exception):
    """可转换为 HTTP JSON 响应的参数或资源错误。"""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def serialize_session(session: Session) -> dict[str, Any]:
    """把内部 Session 转为前端需要的稳定结构，避免直接暴露内部对象。"""
    messages: list[dict[str, Any]] = []
    for message in session.get_messages():
        item: dict[str, Any] = {
            "role": message.get("role", ""),
            "content": message.get("content", ""),
        }
        if message.get("tool_calls"):
            item["tool_calls"] = message["tool_calls"]
        if message.get("tool_call_id"):
            item["tool_call_id"] = message["tool_call_id"]
        messages.append(item)

    return {
        "id": session.session_id,
        "messages": messages,
        "trace": list(session.trace),
        "message_count": session.message_count(),
        "turns": session.user_assistant_turns(),
        "created": session.created_at_str,
        "updated": session.updated_at_str,
    }


def validate_session_id(value: Any) -> str:
    """校验 URL 与会话字典共用的 ID，拒绝路径分隔符和控制字符。"""
    if not isinstance(value, str):
        raise APIError(400, "invalid_session", "session_id 必须是字符串")
    session_id = value.strip()
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise APIError(
            400,
            "invalid_session",
            "session_id 需为 1-64 位字符，不能以空格或标点开头，也不能包含 /",
        )
    return session_id


class AgentWebServer(ThreadingHTTPServer):
    """携带共享 Agent 的 HTTP 服务；锁用于保护内存会话与 ReAct 循环。"""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], agent: Agent):
        super().__init__(address, AgentRequestHandler)
        self.agent = agent
        self.agent_lock = threading.Lock()


class AgentRequestHandler(BaseHTTPRequestHandler):
    """同源静态资源与 /api/* 请求处理器。"""

    server: AgentWebServer
    server_version = "MinimalAgentWeb/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.client_address[0], format % args)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        self._dispatch(self._handle_get)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        self._dispatch(self._handle_post)

    def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        self._dispatch(self._handle_delete)

    def _check_host(self) -> None:
        """
        仅在监听回环地址时校验 Host，防御 DNS rebinding。

        显式绑定 0.0.0.0 或网卡地址时跳过校验，交给用户与防火墙决定。
        """
        bind_host = str(self.server.server_address[0])
        if bind_host not in ("127.0.0.1", "::1", "localhost"):
            return

        raw = (self.headers.get("Host") or "").strip().lower()
        if not raw:
            return

        if raw.startswith("["):                      # IPv6: [::1]:8080
            hostname = raw[1:raw.find("]")] if "]" in raw else raw
        elif ":" in raw:                             # IPv4/host: 127.0.0.1:8080
            hostname = raw.rsplit(":", 1)[0]
        else:
            hostname = raw

        if hostname not in ("127.0.0.1", "localhost", "::1"):
            raise APIError(403, "invalid_host", "Host 头不被允许")

    def _dispatch(self, handler: Any) -> None:
        try:
            self._check_host()
            handler()
        except APIError as error:
            self._write_error(error)
        except (BrokenPipeError, ConnectionResetError):
            logger.debug("客户端提前断开连接")
        except Exception:
            logger.exception("Web 请求处理失败: %s", self.path)
            self._write_error(APIError(500, "internal_error", "服务内部错误，请查看服务端日志"))

    def _handle_get(self) -> None:
        path = unquote(urlsplit(self.path).path)

        if path in STATIC_FILES:
            self._serve_static(path)
            return

        if path == "/api/health":
            llm = self.server.agent.llm
            api_key = getattr(llm, "api_key", "")
            configured = bool(api_key) and not api_key.startswith("sk-your")
            self._write_json(200, {
                "status": "ok",
                "model": getattr(llm, "model", "unknown"),
                "llm_configured": configured,
                "tool_count": len(self.server.agent.tools.list_tools()),
            })
            return

        if path == "/api/tools":
            tools = [
                {
                    "name": schema["function"]["name"],
                    "description": schema["function"]["description"],
                    "parameters": schema["function"]["parameters"],
                }
                for schema in self.server.agent.tools.get_all_tools_schema()
            ]
            self._write_json(200, {"tools": tools})
            return

        if path == "/api/sessions":
            with self.server.agent_lock:
                sessions = self.server.agent.get_sessions()
            sessions.sort(key=lambda item: item["updated"], reverse=True)
            self._write_json(200, {"sessions": sessions})
            return

        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "sessions"]:
            session_id = validate_session_id(parts[2])
            with self.server.agent_lock:
                session = self.server.agent.session_manager.get(session_id)
                payload = serialize_session(session) if session else None
            if payload is None:
                raise APIError(404, "session_not_found", f"会话 {session_id} 不存在")
            self._write_json(200, {"session": payload})
            return

        if path.startswith("/api/"):
            raise APIError(404, "api_not_found", "接口不存在")
        raise APIError(404, "page_not_found", "页面不存在")

    def _handle_post(self) -> None:
        path = unquote(urlsplit(self.path).path)
        body = self._read_json()

        if path == "/api/chat":
            session_id = validate_session_id(body.get("session_id"))
            message = self._validate_message(body)

            with self.server.agent_lock:
                answer = self.server.agent.chat(session_id, message)
                session = self.server.agent.session_manager.get_or_create(session_id)
                payload = serialize_session(session)
            self._write_json(200, {"answer": answer, "session": payload})
            return

        if path == "/api/chat/stream":
            self._handle_chat_stream(body)
            return

        if path == "/api/sessions":
            requested_id = body.get("session_id")
            session_id = (
                validate_session_id(requested_id)
                if requested_id is not None
                else f"web-{uuid.uuid4().hex[:10]}"
            )
            with self.server.agent_lock:
                existed = self.server.agent.session_manager.exists(session_id)
                session = self.server.agent.session_manager.get_or_create(session_id)
                payload = serialize_session(session)
            self._write_json(200 if existed else 201, {"session": payload})
            return

        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "reset":
            session_id = validate_session_id(parts[2])
            with self.server.agent_lock:
                session = self.server.agent.session_manager.get(session_id)
                if session is None:
                    raise APIError(404, "session_not_found", f"会话 {session_id} 不存在")
                session.reset()
                payload = serialize_session(session)
            self._write_json(200, {"session": payload})
            return

        raise APIError(404, "api_not_found", "接口不存在")

    def _validate_message(self, body: dict[str, Any]) -> str:
        """校验并规范化用户消息，普通与流式聊天接口共用。"""
        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            raise APIError(400, "invalid_message", "消息不能为空")
        message = message.strip()
        if len(message) > MAX_MESSAGE_CHARS:
            raise APIError(400, "message_too_long", f"消息不能超过 {MAX_MESSAGE_CHARS} 字")
        return message

    def _handle_chat_stream(self, body: dict[str, Any]) -> None:
        """
        以 SSE 推送 ReAct 执行过程。

        事件序列: start → trace（可多次）→ done | error。
        Agent 仍在独立线程中同步执行；本方法只做 trace 增量读取，
        不复制核心循环，也不与 agent_lock 抢锁。
        """
        session_id = validate_session_id(body.get("session_id"))
        message = self._validate_message(body)

        with self.server.agent_lock:
            session = self.server.agent.session_manager.get_or_create(session_id)
        cursor = len(session.trace)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.close_connection = True

        outcome: dict[str, Any] = {}
        finished = threading.Event()

        def run_agent() -> None:
            try:
                with self.server.agent_lock:
                    outcome["answer"] = self.server.agent.chat(session_id, message)
            except Exception as error:  # noqa: BLE001 - 需要转换成 SSE 事件返回前端
                logger.exception("流式对话失败: %s", session_id)
                outcome["error"] = str(error)
            finally:
                finished.set()

        started_at = time.time()
        threading.Thread(target=run_agent, daemon=True).start()
        self._sse_send("start", {"session_id": session_id, "message": message})

        while not finished.is_set():
            cursor = self._flush_trace(session, cursor)
            finished.wait(0.12)
        self._flush_trace(session, cursor)

        if "error" in outcome:
            self._sse_send("error", {
                "error": {"code": "chat_failed", "message": outcome["error"]},
            })
            return

        with self.server.agent_lock:
            payload = serialize_session(session)
        self._sse_send("done", {
            "answer": outcome.get("answer", ""),
            "session": payload,
            "elapsed": round(time.time() - started_at, 2),
        })

    def _flush_trace(self, session: Session, cursor: int) -> int:
        """推送 cursor 之后新增的 trace 条目，返回新的 cursor。"""
        entries = session.trace[cursor:]
        for entry in entries:
            self._sse_send("trace", {"entry": entry})
        return cursor + len(entries)

    def _sse_send(self, event: str, data: dict[str, Any]) -> None:
        frame = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        self.wfile.write(frame.encode("utf-8"))
        self.wfile.flush()

    def _handle_delete(self) -> None:
        path = unquote(urlsplit(self.path).path)
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "sessions"]:
            session_id = validate_session_id(parts[2])
            with self.server.agent_lock:
                deleted = self.server.agent.session_manager.delete(session_id)
            if not deleted:
                raise APIError(404, "session_not_found", f"会话 {session_id} 不存在")
            self._write_json(200, {"deleted": session_id})
            return
        raise APIError(404, "api_not_found", "接口不存在")

    def _read_json(self) -> dict[str, Any]:
        """限制请求体大小并只接受 JSON 对象，防止异常输入进入核心层。"""
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            raise APIError(415, "unsupported_media_type", "请求体必须使用 application/json")

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise APIError(400, "invalid_length", "Content-Length 不合法") from error
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise APIError(413, "request_too_large", "请求体过大")

        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise APIError(400, "invalid_json", "请求体不是合法 JSON") from error
        if not isinstance(data, dict):
            raise APIError(400, "invalid_json", "JSON 顶层必须是对象")
        return data

    def _serve_static(self, path: str) -> None:
        filename, content_type = STATIC_FILES[path]
        # 路由采用固定映射，不把用户输入拼接为文件路径，从源头避免路径穿越。
        file_path = WEB_ROOT / filename
        if not file_path.is_file():
            raise APIError(404, "page_not_found", "静态资源不存在")
        content = file_path.read_bytes()
        cache_control = "no-cache" if filename == "index.html" else "public, max-age=300"
        self._write_bytes(200, content, content_type, cache_control)

    def _write_error(self, error: APIError) -> None:
        self._write_json(error.status, {
            "error": {"code": error.code, "message": error.message},
        })

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._write_bytes(
            status,
            content,
            "application/json; charset=utf-8",
            "no-store",
        )

    def _write_bytes(
        self,
        status: int,
        content: bytes,
        content_type: str,
        cache_control: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type.startswith("text/html"):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self'; font-src 'self'; object-src 'none'; "
                "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            )
        self.end_headers()
        self.wfile.write(content)


def create_server(host: str, port: int, agent: Agent) -> AgentWebServer:
    """独立工厂，便于测试时注入 MockLLM，也便于其他 Python 模块嵌入 Web UI。"""
    return AgentWebServer((host, port), agent)


def run(host: str = "127.0.0.1", port: int = 8080, agent: Agent | None = None) -> None:
    """启动服务；未注入 Agent 时复用 main.py 的现有装配逻辑。"""
    if agent is None:
        from main import build_agent

        agent = build_agent()

    server = create_server(host, port, agent)
    actual_host, actual_port = server.server_address
    print(f"Minimal Agent Web: http://{actual_host}:{actual_port}")
    print("按 Ctrl+C 停止服务；会话仅保存在内存中。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 Minimal Agent Web...")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Agent Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    parser.add_argument("--port", type=int, default=8080, help="监听端口，默认 8080")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
