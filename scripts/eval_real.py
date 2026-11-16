"""
真实模型小样本评测。

用途: 用固定问题集跑一遍真实模型，记录通过率、步数、耗时与 token 消耗，
     作为"能跑通真实 API"的可复现证据，而不是仅靠单元测试。

运行:
    python scripts/eval_real.py

前置:
    .env 中配置可用的 LLM_API_KEY（会产生少量 token 消耗）

输出:
    docs/评测记录.md + 终端汇总
"""

from __future__ import annotations

import platform
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from main import build_agent  # noqa: E402

OUTPUT = ROOT / "docs" / "评测记录.md"

# 覆盖题目要求的四种能力：直接回答、工具调用、多轮记忆、跨工具协作。
CASES: list[dict[str, Any]] = [
    {
        "id": "direct",
        "kind": "直接回答",
        "question": "用一句话说明 Agent 和普通聊天机器人的区别。",
        "expect_any": ["工具", "行动", "决策", "调用"],
    },
    {
        "id": "calculator",
        "kind": "工具·计算",
        "question": "请计算 (128 + 64) * 3 等于多少？只回答结果和一步算式。",
        "expect_all": ["576"],
        "expect_tool": "calculator",
    },
    {
        "id": "search",
        "kind": "工具·搜索",
        "question": "搜索一下 ReAct，并给出一句话总结。",
        "expect_any": ["推理", "行动", "ReAct"],
        "expect_tool": "search",
    },
    {
        "id": "todo",
        "kind": "工具·待办",
        "question": "帮我添加一条待办：周五前整理 Agent 学习笔记。",
        "expect_any": ["待办", "笔记"],
        "expect_tool": "todo_list",
    },
    {
        "id": "multi_turn",
        "kind": "多轮记忆",
        "question": "请记住这个数字：42。",
        "followup": "我刚才让你记住的数字是多少？只回答数字。",
        "expect_all": ["42"],
    },
]


class UsageTracker:
    """包装 LLMClient.chat，累计 token 用量（不修改核心代码）。"""

    def __init__(self, agent: Any) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0
        original = agent.llm.chat

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            response = original(*args, **kwargs)
            usage = response.usage or {}
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.completion_tokens += int(usage.get("completion_tokens") or 0)
            self.calls += 1
            return response

        agent.llm.chat = wrapped

    def reset(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0


def judge(case: dict[str, Any], answer: str, tools: list[str]) -> tuple[bool, str]:
    if case.get("expect_all"):
        missing = [word for word in case["expect_all"] if word not in answer]
        if missing:
            return False, f"回答缺少关键词: {', '.join(missing)}"
    if case.get("expect_any") and not any(word in answer for word in case["expect_any"]):
        return False, "回答未命中任一预期关键词"
    if case.get("expect_tool") and case["expect_tool"] not in tools:
        return False, f"未调用预期工具 {case['expect_tool']}"
    return True, "通过"


def run_case(agent: Any, tracker: UsageTracker, case: dict[str, Any]) -> dict[str, Any]:
    session_id = f"eval-{case['id']}-{int(time.time() * 1000)}"
    tracker.reset()
    started = time.perf_counter()

    error = ""
    try:
        answer = agent.chat(session_id, case["question"])
        if case.get("followup"):
            answer = agent.chat(session_id, case["followup"])
    except Exception as exc:  # noqa: BLE001 - 评测需要把失败也记录下来
        answer = ""
        error = f"{type(exc).__name__}: {exc}"

    elapsed = time.perf_counter() - started
    trace = agent.get_trace(session_id) or ""
    steps = [int(value) for value in re.findall(r"Step (\d+)/\d+", trace)]
    tools = re.findall(r"Tool call: ([\w-]+)\(", trace)

    if error:
        passed, reason = False, error
    else:
        passed, reason = judge(case, answer, tools)

    return {
        "id": case["id"],
        "kind": case["kind"],
        "passed": passed,
        "reason": reason,
        "steps": max(steps) if steps else 0,
        "tools": "、".join(dict.fromkeys(tools)) or "—",
        "elapsed": elapsed,
        "prompt_tokens": tracker.prompt_tokens,
        "completion_tokens": tracker.completion_tokens,
        "answer": answer.strip().replace("\n", " ")[:120],
    }


def render(results: list[dict[str, Any]], model: str) -> str:
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    avg_time = sum(item["elapsed"] for item in results) / total
    prompt_tokens = sum(item["prompt_tokens"] for item in results)
    completion_tokens = sum(item["completion_tokens"] for item in results)
    total_tokens = prompt_tokens + completion_tokens

    lines = [
        "# 真实模型评测记录",
        "",
        "> 由 `scripts/eval_real.py` 自动生成。单次运行、小样本，用于验证真实 API 链路，"
        "不作为模型能力的严格 benchmark。",
        "",
        "## 运行信息",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 运行时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |",
        f"| 模型 | `{model}` |",
        f"| Python | {platform.python_version()} |",
        f"| 用例数 | {total} |",
        "",
        "## 结果",
        "",
        "| 用例 | 类型 | 结果 | 最大步数 | 工具 | 耗时 | prompt / completion tokens |",
        "|---|---|---|:---:|---|---:|---|",
    ]

    for item in results:
        mark = "✅ 通过" if item["passed"] else "❌ 失败"
        lines.append(
            f"| {item['id']} | {item['kind']} | {mark} | {item['steps']} | {item['tools']} | "
            f"{item['elapsed']:.2f}s | {item['prompt_tokens']} / {item['completion_tokens']} |"
        )

    lines += [
        "",
        "## 汇总",
        "",
        f"- 通过率：**{passed}/{total}**",
        f"- 平均耗时：**{avg_time:.2f}s / 用例**",
        f"- token 消耗：prompt {prompt_tokens} + completion {completion_tokens} = **{total_tokens}**",
        "",
        "## 失败详情",
        "",
    ]

    failures = [item for item in results if not item["passed"]]
    if not failures:
        lines.append("无。")
    else:
        for item in failures:
            lines.append(f"- `{item['id']}`：{item['reason']}")
            lines.append(f"  - 实际回答：{item['answer'] or '(空)'}")

    lines += [
        "",
        "## 复现方式",
        "",
        "```bash",
        "python scripts/eval_real.py",
        "```",
        "",
        "说明：模型输出存在随机性，重跑结果可能不同；失败项会保留原始回答，便于定位是提示词问题还是模型能力问题。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    agent = build_agent()
    tracker = UsageTracker(agent)
    model = getattr(agent.llm, "model", "unknown")

    print(f"开始评测：model={model}, cases={len(CASES)}")
    results = []
    for index, case in enumerate(CASES, start=1):
        print(f"[{index}/{len(CASES)}] {case['id']} ...", end=" ", flush=True)
        result = run_case(agent, tracker, case)
        results.append(result)
        print("PASS" if result["passed"] else f"FAIL ({result['reason']})")

    report = render(results, model)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(report, encoding="utf-8")

    passed = sum(1 for item in results if item["passed"])
    print(f"\n完成：{passed}/{len(results)} 通过；报告写入 {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
