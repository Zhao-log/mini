"""
Search — Mock 搜索引擎工具。

用预设的 mock 数据库，模拟搜索返回。
如果想接真实搜索，可以把 handler 换成调 Bing/DuckDuckGo API。
"""

from __future__ import annotations

from typing import Any

from . import Tool


# Mock 数据: query keyword → 结果列表
_MOCK_DB: dict[str, list[str]] = {
    "python": [
        "Python 是一种高级编程语言，由 Guido van Rossum 于 1991 年首次发布。",
        "Python 3.12 于 2023 年 10 月发布，带来了新的语法和性能提升。",
        "Python 的优势: 语法简洁、生态丰富、适合 AI/ML 领域（PyTorch, TensorFlow, LangChain 等）。",
    ],
    "agent": [
        "AI Agent 是能够自主规划、调用工具、多轮推理的智能体。",
        "ReAct (Reasoning + Acting) 模式是当前主流 Agent 架构的基础。",
        "LangGraph、AutoGen、OpenHands 是流行的 Agent 开发框架。",
    ],
    "llm": [
        "LLM (Large Language Model) 大语言模型，代表模型: GPT-4, Claude 3, Gemini, 文心一言。",
        "2024 年主流模型都支持 function calling / tool use，使 Agent 成为可能。",
        "本地可运行的 LLM 选择: Llama 3, Qwen, Mistral, Gemma。",
    ],
    "new york": [
        "纽约市 (New York City) 位于美国东海岸，人口约 850 万。",
        "主要地标: 自由女神像、帝国大厦、中央公园、华尔街、时代广场。",
        "纽约是全球金融、艺术、文化中心。",
    ],
    "天气": [
        "当前 mock 天气: 晴，22°C，湿度 45%，微风。",
        "明天预期: 多云转小雨，18-25°C。",
    ],
    "股票": [
        "提示: mock 搜索不提供实时股票数据。",
        "请使用真实金融 API 获取实时行情。",
    ],
}


def _search_mock(query: str) -> str:
    """在 mock DB 里做关键字匹配搜索."""
    q = query.lower().strip()

    if not q:
        return "❌ 搜索关键词不能为空"

    results = []
    for keyword, items in _MOCK_DB.items():
        if q in keyword or keyword in q:
            results.extend(items)

    if not results:
        # 模糊匹配：只要有一个词匹配
        words = q.split()
        for keyword, items in _MOCK_DB.items():
            kw_lower = keyword.lower()
            if any(w in kw_lower or kw_lower in w for w in words):
                results.extend(items)

    if not results:
        return f'🔍 搜索 "{query}" 未找到相关结果。当前 mock 数据包含: {", ".join(_MOCK_DB.keys())}'

    output = f'🔍 搜索结果 — "{query}":\n\n'
    for i, r in enumerate(results[:5], 1):
        output += f"{i}. {r}\n"
    return output.strip()


def search_handler(query: str) -> str:
    return _search_mock(query)


SEARCH_TOOL = Tool(
    name="search",
    description=(
        "搜索引擎，根据关键词搜索信息。"
        "当前为 mock 实现，内置了 Python、Agent、LLM、纽约、天气、股票 等主题的预设结果。"
        "真实部署时可以替换为 Bing/DuckDuckGo/Google 搜索 API。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，如 'python 3.12 新特性'、'AI Agent 框架'",
            }
        },
        "required": ["query"],
    },
    handler=search_handler,
)
