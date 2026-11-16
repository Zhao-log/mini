"""
兼容性测试.

覆盖:
  - Python 运行版本要求（>=3.10，代码使用了 X | None 语法）
  - Windows 中文控制台编码（GBK / cp936）下 CLI 不崩溃
  - UTF-8 控制台下 CLI 正常启动与退出
  - 依赖可用性
  - 供应商响应格式差异（原生 tool_calls / 空 content / content 为数组）

说明: 本项目是 CLI 应用（非 Web 前端），因此"浏览器兼容性"不适用，
      兼容性验证聚焦于运行时环境与模型供应商协议差异。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 运行时版本与依赖
# ---------------------------------------------------------------------------

def test_python_version_supported():
    """项目使用 PEP 604 联合类型（str | None），要求 Python >= 3.10."""
    assert sys.version_info >= (3, 10), f"需要 Python >= 3.10，当前 {sys.version}"


def test_core_dependencies_importable():
    import httpx
    import dotenv

    assert hasattr(httpx, "Client")
    assert hasattr(dotenv, "load_dotenv")


def test_source_compiles_under_current_interpreter():
    """所有源码应能在当前解释器下编译（语法兼容）."""
    import compileall

    ok = compileall.compile_dir(
        os.path.join(ROOT, "src"), quiet=2, force=False, legacy=False
    )
    assert ok, "src 下存在无法编译的模块"


# ---------------------------------------------------------------------------
# CLI 在中文 Windows 控制台（GBK）下的兼容性
# ---------------------------------------------------------------------------

def _run_cli(env_extra: dict[str, str], stdin: str, output_encoding: str):
    env = os.environ.copy()
    env.update(env_extra)
    env.setdefault("LLM_API_KEY", "sk-test-key")
    env.setdefault("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    env.setdefault("LLM_MODEL", "fake-model")
    return subprocess.run(
        [sys.executable, "main.py"],
        input=stdin,
        capture_output=True,
        text=True,
        encoding=output_encoding,
        errors="replace",
        cwd=ROOT,
        env=env,
        timeout=60,
    )


def test_cli_runs_under_utf8_console():
    proc = _run_cli({"PYTHONIOENCODING": "utf-8"}, "/help\n/quit\n", "utf-8")
    assert proc.returncode == 0, f"stderr: {proc.stderr[-2000:]}"
    assert "Minimal Agent" in proc.stdout
    assert "calculator" in proc.stdout


def test_cli_runs_under_gbk_console():
    """
    中文 Windows 的 cmd.exe 默认代码页是 936(GBK)。
    CLI 输出含 emoji 和中文，若不做处理会抛 UnicodeEncodeError 直接崩溃。
    """
    proc = _run_cli({"PYTHONIOENCODING": "gbk"}, "/quit\n", "gbk")
    assert proc.returncode == 0, (
        "GBK 控制台下 CLI 崩溃（UnicodeEncodeError）。\n"
        f"stderr: {proc.stderr[-2000:]}"
    )


def test_cli_handles_eof_gracefully():
    """直接关闭输入（EOF）应优雅退出而不是抛异常."""
    proc = _run_cli({"PYTHONIOENCODING": "utf-8"}, "", "utf-8")
    assert proc.returncode == 0, f"stderr: {proc.stderr[-2000:]}"


def test_cli_missing_api_key_warns(tmp_path):
    """未配置 API Key 时应给出提示但仍能启动。

    load_dotenv() 会从 main.py 所在目录向上查找 .env，与 cwd 无关，
    因此这里显式把 LLM_API_KEY 置空（load_dotenv 默认不覆盖已存在的变量），
    模拟"未配置/配置为空"的场景。
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["LLM_API_KEY"] = ""
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "main.py")],
        input="/quit\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "LLM_API_KEY" in proc.stdout


# ---------------------------------------------------------------------------
# 供应商协议差异（离线校验，不启动服务）
# ---------------------------------------------------------------------------

class TestProviderVariance:
    def test_qwen_reasoning_content(self):
        """通义千问会额外返回 reasoning_content，应被用作 thought."""
        from src.llm_client import LLMClient
        from src.parser import parse_llm_response
        import json

        message = {
            "content": None,
            "reasoning_content": "先算乘法",
            "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "calculator", "arguments": json.dumps({"expression": "1+1"})},
            }],
        }
        parsed = parse_llm_response(LLMClient._coerce_content(message))
        assert parsed.action == "tool_call"
        assert parsed.thought == "先算乘法"

    def test_content_as_array(self):
        from src.llm_client import LLMClient

        msg = {"content": [{"type": "text", "text": '{"action":"final_answer","answer":"ok"}'}]}
        assert "final_answer" in LLMClient._coerce_content(msg)

    def test_empty_choices_error(self, monkeypatch):
        """choices 为空时应抛受控 RuntimeError，而不是 KeyError/IndexError."""
        from src.llm_client import LLMClient

        client = LLMClient(api_key="x")
        monkeypatch.setattr(client, "_post", lambda *a, **kw: {"choices": []})

        with pytest.raises(RuntimeError, match="choices"):
            client.chat([{"role": "user", "content": "hi"}])

    def test_malformed_response_missing_message(self, monkeypatch):
        """choices 存在但缺少 message 时，应降级为 final_answer 而不是崩溃."""
        from src.llm_client import LLMClient
        from src.parser import parse_llm_response

        client = LLMClient(api_key="x")
        monkeypatch.setattr(client, "_post", lambda *a, **kw: {"choices": [{}]})

        resp = client.chat([{"role": "user", "content": "hi"}])
        parsed = parse_llm_response(resp.content)
        assert parsed.action == "final_answer"
