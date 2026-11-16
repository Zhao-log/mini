﻿# Minimal Agent — 从零实现的最小可用 Agent

> 笔试题要求：不依赖 langgraph / openhands / openclaw 等现有 Agent 框架，核心 Runtime 自行实现。

## ✨ 一句话介绍

**Agent = LLM（大脑） + Tools（手脚） + ReAct Loop（边想边做）**

这就是这个项目的本质。一个约 1200 行 Python 代码的最小 Agent，用 `httpx` 手写 HTTP 调用 OpenAI-compatible 接口，核心循环不依赖任何 Agent 框架。

```
用户输入 → LLM 决策 → 调工具 or 直接回答 → 循环 or 结束
```

## 📦 项目结构

```
minimal-agent/
├── src/
│   ├── agent.py          # 核心 ReAct 循环  ⭐心脏
│   ├── llm_client.py     # 手写 HTTP，零 SDK
│   ├── parser.py         # LLM 输出 JSON 解析 + 容错
│   ├── memory.py         # Context 管理（过滤/截断/压缩）
│   ├── sessions.py       # Session 隔离（多窗口）
│   ├── exceptions.py     # 异常定义
│   └── tools/
│       ├── __init__.py   # ToolRegistry 注册中心
│       ├── calculator.py # 安全计算器
│       ├── search.py     # mock 搜索引擎
│       └── todo_list.py  # 待办事项管理
├── tests/                # 核心、集成与 Web API 测试
├── docs/
│   └── 代码逐行导读.md    # 面向 Python 新手的全量代码讲解
├── web/                  # 原生 Web 工作台（无前端构建步骤）
│   ├── index.html        # 语义化布局与静态模板
│   ├── styles.css        # 三栏布局、移动抽屉与交互状态
│   ├── api.js            # 同源 API 客户端（含 SSE 解析）与错误规范化
│   └── app.js            # 页面状态、会话和消息交互
├── .github/workflows/tests.yml  # CI：Python 3.10 / 3.12 跑全量测试
├── web_server.py         # 标准库 HTTP 服务与 Agent API 适配层
├── main.py               # CLI 入口
├── pyproject.toml        # ruff / mypy / pytest 配置
├── requirements.txt      # 运行时依赖
├── requirements-dev.txt  # 测试与静态检查依赖
├── .env.example          # API Key 占位符（永远不提交真实 key）
├── .gitignore            # .env 在里面，确保不会进 Git
└── README.md
```

## 🚀 快速开始

```bash
# 1. 安装运行时依赖
pip install -r requirements.txt

# 2. 配置 API Key（复制 .env.example 为 .env）
cp .env.example .env
# 然后编辑 .env，填入真实的 LLM_API_KEY

# 3. 跑测试（不需要 API Key，用 MockLLM）
pip install -r requirements-dev.txt
python -m pytest tests/ -v

# 4. 启动交互式 CLI
python main.py

# 5. 或启动 Web 工作台，访问 http://127.0.0.1:8080
python web_server.py
```

CLI 命令：
```
/session <id>   切换或创建 session（不同 session 隔离上下文）
/sessions       列出所有 session
/trace          查看当前 session 的执行 trace
/reset          清空当前 session
/tools          列出已注册的工具
/help           显示帮助
/quit           退出
```

工程检查（可选，依赖在 `requirements-dev.txt`）：

```bash
python -m ruff check .                 # 静态检查
python -m mypy                          # 类型检查，配置见 pyproject.toml
coverage run --source=src -m pytest tests/ -q && coverage report
```

## Web 工作台

```bash
python web_server.py
# 自定义监听地址或端口
python web_server.py --host 127.0.0.1 --port 8080
```

浏览器访问 `http://127.0.0.1:8080`。页面无需 npm、Node.js 或前端构建，也不会增加 `requirements.txt` 依赖。桌面端提供会话导航、对话区、执行轨迹/工具检查区；窄屏下两侧栏变为抽屉。

基础操作：

- 新建、切换会话，或清空当前会话消息（保留 trace）。
- 消息通过 SSE 流式返回：右侧轨迹随 Agent 执行实时更新，回答完成后一次性呈现。
- `Enter` 发送，`Shift + Enter` 换行，输入最多 4000 字；非输入状态下按 `N` 新建会话。
- 点击示例只填充输入框，不会自动发送。
- 右侧“执行轨迹”查看 ReAct 决策，“可用工具”查看 ToolRegistry 提供的 JSON Schema。
- 会话和待办仍只保存在进程内存中，服务重启后清空；默认只监听 `127.0.0.1`，不要直接暴露到公网。

### Web API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 服务、模型配置与工具数量（不返回密钥） |
| GET | `/api/tools` | 工具名称、描述和参数 Schema |
| GET | `/api/sessions` | 会话概览列表 |
| POST | `/api/sessions` | 新建会话，可省略 `session_id` 自动生成 |
| GET | `/api/sessions/<id>` | 完整消息与执行轨迹 |
| DELETE | `/api/sessions/<id>` | 删除会话及其内存状态 |
| POST | `/api/chat` | 一次性调用 `Agent.chat()`，返回完整回答 |
| POST | `/api/chat/stream` | SSE 流式对话，事件序列 `start → trace* → done/error` |
| POST | `/api/sessions/<id>/reset` | 清空消息并保留轨迹 |

错误统一返回 `{"error": {"code": "...", "message": "..."}}`。静态资源与 API 同源，无需配置 CORS。服务监听回环地址时会校验 `Host` 头，防御 DNS rebinding；显式绑定 `0.0.0.0` 时跳过该校验。

### 前端扩展接口

- `web/api.js` 的 `agentApi` 集中封装所有请求；新增核心能力时先在这里增加方法，再在 `app.js` 接入状态与交互。
- `web/app.js` 的 `state.currentSession` 是当前会话唯一状态源；动态模型文本通过 `textContent` 渲染，避免把模型输出当作 HTML。
- `web_server.py` 只负责协议、校验和序列化。不要在 Web 层复制 ReAct、上下文压缩或工具执行逻辑。
- 嵌入其他 Python 程序或编写测试时，使用 `create_server(host, port, agent)` 注入已装配的 Agent；`run(agent=...)` 也支持依赖注入。
- 修改样式时复用 `styles.css` 顶部的颜色、字体变量。移动端断点为 820px 和 1180px，并支持键盘焦点与减少动态效果偏好。

## 🏗️ 系统设计

### 模块职责

| 模块 | 职责 | 为什么这样设计 |
|------|------|----------------|
| `Agent` | 核心 ReAct 循环 | 手写 while-for 循环，条件分支判断 tool_call vs final_answer，没有用任何 Agent SDK |
| `LLMClient` | HTTP 调用 | 用 httpx 手写 OpenAI Chat Completions 请求体，不用 openai SDK 的自动 tool_call 解析 |
| `Parser` | 提取 JSON | 三级容错（直接解析 → 代码块 → 大括号），失败降级为 final_answer |
| `ToolRegistry` | 工具注册 | Tool 用 JSON Schema 定义参数，LLM 基于 schema 自主决策 |
| `SessionManager` | 多窗口隔离 | 内存 dict，按 session_id 隔离 messages 和 trace |
| `ContextManager` | 上下文管理 | **自行判断**哪些塞入 context |

### ReAct 循环（`agent.py` 的核心）

```python
for step in range(max_steps):
    # 1. 构建 context（经过过滤/截断/压缩）
    context = context_manager.build_context(session.messages)
    
    # 2. 调 LLM → 决策
    response = llm.chat(context, tools=tool_schemas)
    parsed = parse_llm_response(response.content)
    
    # 3. 判断分支
    if parsed.action == "final_answer":
        return parsed.final_answer          # 结束
    elif parsed.action == "tool_call":
        result = tools.execute(name, args)  # 执行工具
        session.add_message(result)         # 回填
        continue                            # 循环继续
```

### LLM 输出协议（自己定的 JSON）

不让 SDK 帮我做 function calling 的解析。在 system prompt 里告诉模型严格输出这种 JSON：

```json
{
  "thought": "思考过程（可以写中文）",
  "action": "tool_call" | "final_answer",
  "tool_name": "工具名（action=tool_call 时必填）",
  "tool_args": {"key": "value"},
  "answer": "最终回答（action=final_answer 时必填）"
}
```

同时在 API 请求里设置 `response_format: {"type": "json_object"}` 强制模型输出 JSON。

### Memory 召回时机与放置方式

**召回时机**：每轮 `agent.chat()` 调用时，`ContextManager.build_context()` 从 `session.messages` 构建要发给 LLM 的 context。

**哪些信息塞进 context**（题目考点："自行判断"）：

| 信息 | 塞进去？ | 理由 |
|------|:---:|------|
| 用户输入（user） | ✅ 全部 | LLM 需要知道用户说了什么 |
| LLM 最终回答（assistant content） | ✅ 全部 | LLM 需要记住自己说过什么 |
| 工具调用记录（assistant tool_calls） | ✅ 保留 | LLM 需要知道自己之前调过什么工具 |
| 工具执行结果（tool content） | ⚠️ 截断到 500 字符 | 太长浪费 token，但 LLM 需要知道结论 |
| LLM 思考过程（thought） | ❌ 不塞 | **LLM 不需要看之前的思考，只需要看事实** — 这是关键设计决策 |

**压缩策略**（基础版）：
- 轮次截断：`MAX_ROUNDS = 20`，只保留最近 20 轮 user+assistant
- 字符上限：`MAX_CHARS = 16000`（粗略估算 token 数，不依赖 tiktoken）
- 超限压缩：把最早的 N 轮消息合并成一条 `system` 级别的 summary，格式如：
  ```
  [历史对话概要（已压缩）]:
    - 用户问: 今天天气怎么样
      → 回答: mock 晴 22°C
    - 用户问: 股票行情
      → 回答: mock 不提供实时数据
  ```

### System Prompt 设计

```
你是一个智能 Agent，可以理解用户问题并自主决定是否使用工具。

## 可用工具
{动态插入 tool_schemas 转换的纯文本描述}

## 输出格式（严格遵守，只输出 JSON）
{固定的 JSON schema 模板}

## 决策规则
1. 能直接回答就 final_answer
2. 需要工具就 tool_call
3. 工具执行完给 final_answer，不要重复调用相同工具
4. 如果工具失败，分析原因后重试或换策略
```

### 工具安全

`calculator` 工具用 `ast.parse` + 白名单节点类型实现安全求值，不使用 `eval()`。已拦截的危险操作：
- `__import__('os')` → 拦截
- `open('/etc/passwd')` → 拦截
- `exec()` / `compile()` → 拦截

### 异常处理

| 异常 | 处理 |
|------|------|
| LLM API 失败 | 返回友好错误 + 记录 trace |
| LLM 输出非 JSON | 三级降级 → 最终兜底为 final_answer |
| 工具不存在 | `ToolNotFoundError` → 转成错误信息给 LLM |
| 工具执行失败 | `ToolExecutionError` → 同上 |
| context 过长 | ContextManager 自动截断 + 基础压缩 |
| session 不存在 | SessionManager 自动创建 |

## 🛠️ 技术栈

| 组件 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.10+ | 生态好、写得快、类型提示好 |
| HTTP | httpx | 比 requests 更现代，支持同步/异步 |
| LLM 调用 | 手写 HTTP | **不让 SDK 帮我藏逻辑**，面试官能看出核心 Runtime 是自己写的 |
| JSON 解析 | 标准库 json + re | 零额外依赖 |
| AST 安全求值 | ast 模块 | Python 内置，白名单机制 |
| 测试 | pytest | 164 个用例（160 通过 + 4 真实 API 跳过），核心覆盖率 93% |
| 日志 | Python logging | 标准库 |

## 📝 测试覆盖

```bash
python -m pytest tests/ -v          # 全量：160 通过 / 4 跳过
python -m pytest tests/ -m "not real" 
# 真实 API 冒烟（需 .env 配置真实 Key，会产生少量 token 消耗）
$env:RUN_REAL_API="1"; python -m pytest tests/test_real_api.py -v
```

```
tests/test_agent.py        9 个  — 核心循环（direct_answer / tool_call / multi_turn / isolation / max_steps / trace）
tests/test_tools.py       25 个  — 工具注册 + 三个工具全功能 + 安全拦截
tests/test_sessions.py     6 个  — session 隔离 + reset + CRUD
tests/test_memory.py      10 个  — 过滤 + 截断 + 压缩 + 全流程
tests/test_parser.py      10 个  — JSON 解析 + 三级容错 + 降级
tests/test_integration.py 11 个  — 本地假 OpenAI 服务端，真实 HTTP 全链路 + 线上协议校验
tests/test_edge_cases.py  58 个  — 边界/异常/DoS/超长/Unicode/防御性校验
tests/test_compat.py      11 个  — Python 版本 / GBK 控制台 / EOF / 供应商协议差异
tests/test_real_api.py     4 个  — 真实模型冒烟（默认跳过，需 RUN_REAL_API=1）
tests/test_web.py         20 个  — 静态资源 / Web API / SSE 流式 / 会话删除 / Host 校验
```

行覆盖率（`src/`）：**93%**。详细结果见 [TEST_REPORT.md](TEST_REPORT.md)。

## 🛡️ API Key 安全

**这是硬性要求**，千万不要把 API Key 提交到 Git：

1. `.env.example` 只放占位符 `sk-your-api-key-here`
2. `.gitignore` 包含 `.env`，确保真实 key 不会被提交
3. 代码里永远是 `os.environ.get("LLM_API_KEY")`，不会硬编码

## 💡 设计决策速查

| 决策 | 理由 |
|------|------|
| 手写 httpx，不用 openai SDK | SDK 帮你做了 tool_call 解析，等于"用了框架" |
| 强制 response_format=json_object | 比让模型自由输出更稳，parser 逻辑更简单 |
| thought 不塞进 context | LLM 不需要看之前的思考，省 token |
| MockLLM 预设响应序列 | 测试不需要真实 API，速度快、可重复 |
| 内存存储 session / todo_list | 简单可靠，demo 够用；要持久化可以加 SQLite |
| 字符数 / 4 估 token | 不依赖 tiktoken，跨模型通用 |
| Web 层用标准库 + 原生前端 | 项目没有前端工程，避免为展示引入 Node 构建链 |
| Web 只做协议适配，不写循环 | 保证 CLI 与 Web 共享同一份 ReAct 实现 |

## 🆚 为什么不用 LangGraph / OpenHands

这是这类题目最常被追问的一点，结论是：**需求本身就是"手写 Runtime"，用框架等于绕过考点**。

| 维度 | 本实现 | LangGraph 等框架 |
|---|---|---|
| 循环控制 | `for step in range(max_steps)` 显式可读 | 由图的节点/边与运行时驱动，需要先学其抽象 |
| LLM 协议 | 自定义 JSON + 三级 parser，逻辑全部可见 | SDK/框架隐藏 function calling 解析 |
| Context 取舍 | `ContextManager` 明确决定塞什么、截多长 | 需要适配框架的 message 管理约定 |
| 可调试性 | trace 是纯文本，可逐行打印 | 依赖框架回调与可视化 |
| 依赖体积 | 2 个运行时依赖（httpx、python-dotenv） | 数十个传递依赖，升级面更大 |

代价也需要说清楚：本实现没有持久化、没有并发任务调度、没有图级别的分支编排。这些正是框架的价值所在，属于"上生产时再引入"的部分。

## 📚 延伸阅读

- [代码逐行导读](docs/代码逐行导读.md)：面向有 Java 基础、没写过 Python 的读者，按文件讲解每一行代码。
- [测试报告](TEST_REPORT.md)：测试范围、覆盖率与缺陷记录。
- [真实模型评测记录](docs/评测记录.md)：固定问题集的通过率、步数、耗时与 token 消耗。

## 📄 提交内容

- ✅ GitHub 仓库链接
- ✅ README（运行方式、系统设计、memory 召回时机与放置方式）
- ✅ 测试用例（164 个，含 Web API 与流式接口）
- ✅ .env.example（API Key 占位符）
- ✅ .gitignore（确保 .env 不进 Git）
- ✅ CI 配置（GitHub Actions 跑双版本测试与覆盖率门槛）
