# 测试报告 — Minimal Agent

| 项 | 内容 |
|---|---|
| 被测系统 | Minimal Agent（从零实现的 Agent Runtime：CLI + Web 工作台） |
| 版本 | 当前工作区快照 |
| 测试日期 | 2026-11-15 |
| 测试环境 | Windows 10/11 · Python 3.14.6 (Anaconda) · PowerShell 5 · Chromium（Playwright 驱动） |
| 被测依赖 | httpx 0.28.1 · python-dotenv 1.2.1 · pytest 9.2.0 · coverage 7.17.3 |
| 真实模型 | 阿里云 DashScope 兼容模式（`qwen3.8-flash`，由 `.env` 配置） |
| 结论 | **通过**：160 通过 / 0 失败 / 4 跳过；行覆盖率 94%；真实模型评测 5/5；阻断级、严重级缺陷全部修复并回归通过 |

---

## 1. 测试范围与方法

覆盖 **CLI 与 Web 两个入口**。Web 层只做 HTTP 协议、校验与序列化，ReAct 核心与 CLI 共用同一份实现，因此核心逻辑以单元/集成测试为主，Web 以真实 HTTP 往返验证。

| 层次 | 手段 | 用例数 | 说明 |
|---|---|---:|---|
| 单元测试 | pytest | 60 | 既有 parser / tools / sessions / memory / agent 用例 |
| 集成测试 | 本地假 OpenAI 服务端（真实 socket + HTTP 往返） | 11 | 校验线上协议、全链路、错误降级、会话隔离 |
| 边界与异常 | pytest | 58 | 超长输入、递归、DoS、Unicode、类型错误、受控失败 |
| 兼容性 | 子进程 / 版本 / 协议差异 | 11 | GBK 控制台、EOF、Python 版本、供应商响应差异 |
| Web 适配层 | 真实 HTTP + MockLLM（随机端口） | 20 | 静态资源、会话 CRUD、SSE 流式、Host 校验、输入校验 |
| 真实环境冒烟 | 真实 DashScope API | 4 | 直答、工具调用、多轮记忆、会话隔离（默认跳过） |
| 真实模型评测 | 固定问题集脚本 `scripts/eval_real.py` | 5 | 通过率、步数、耗时、token 消耗 |

执行命令：

```powershell
python -m pytest tests/                                   # 160 passed, 4 skipped
$env:RUN_REAL_API="1"; python -m pytest tests/test_real_api.py -v   # 4 passed（真实模型）
python scripts/eval_real.py                               # 5/5 通过，生成 docs/评测记录.md
```

---

## 2. 覆盖率

`coverage run --source=src -m pytest tests/` → **总覆盖率 94%（723 语句 / 41 未覆盖）**

| 模块 | 语句数 | 未覆盖 | 覆盖率 |
|---|---:|---:|---:|
| `src/__init__.py` | 7 | 0 | 100% |
| `src/exceptions.py` | 5 | 0 | 100% |
| `src/sessions.py` | 66 | 0 | 100% |
| `src/tools/__init__.py` | 65 | 2 | 97% |
| `src/memory.py` | 105 | 4 | 96% |
| `src/tools/calculator.py` | 77 | 5 | 94% |
| `src/tools/search.py` | 27 | 1 | 96% |
| `src/agent.py` | 88 | 6 | 93% |
| `src/llm_client.py` | 122 | 9 | 93% |
| `src/tools/todo_list.py` | 66 | 5 | 92% |
| `src/parser.py` | 95 | 9 | 91% |
| **合计** | **723** | **41** | **94%** |

未覆盖部分主要是防御性兜底分支（不可达路径）与 CLI 交互分支。
`main.py` 通过子进程黑盒测试覆盖（启动 / 空格命令 / `/help` / `/quit` / EOF / 缺 Key），因运行在独立进程，未计入行覆盖率；`web_server.py` 由 20 个真实 HTTP 用例覆盖。

---

## 3. 功能验证结论

| 需求 | 验证方式 | 结果 |
|---|---|---|
| 不依赖 Agent 框架，Runtime 自研 | 代码审查：无 langgraph/openhands/openclaw 等依赖，仅 httpx + dotenv | 通过 |
| Loop 四步（收输入 → 判断 → 调工具 → 判继续/返回） | IT-02/03 真实 HTTP 往返验证请求序列与消息角色序列 | 通过 |
| ≥3 个工具 + JSON Schema 注册 | 功能测试 + IT-01 校验 `tools` 数组含 3 项且结构完整 | 通过 |
| LLM 自主决策调用（Schema 驱动） | 真实模型测试：自动选择 calculator 得 7006652 | 通过 |
| LLM 输出解析（思考/工具调用/最终答案） | parser 10 用例 + 三级容错 + 原生 tool_calls 兼容 | 通过 |
| Session 管理（窗口 1/2 独立） | 单元 + IT-06 + 真实模型隔离测试 | 通过 |
| Context 有效管理（轮次上限/记忆/追问/压缩） | memory 10 用例 + 边界 4 用例（截断、压缩、system 合并） | 通过 |
| 思考过程是否进 context（自行判断） | 设计为仅入 trace；IT-02 断言第二次请求 assistant.content 为空 | 通过 |
| 基本异常处理 | 上游 500/401、工具不存在、工具内部异常、解析失败、空响应 | 通过 |
| 工具调用 trace / 执行日志 | 单元断言 trace 含 Step、tool、Final Answer | 通过 |
| API Key 不落代码 | `.env` + `.gitignore`；代码仅读环境变量 | 通过 |

---

## 4. 缺陷清单

共发现并修复 15 个缺陷，其中**阻断 1 个、严重 5 个、一般 9 个**。全部已回归。

### 🔴 阻断级

#### D-01 多轮工具调用在真实 API 上必然 400 失败

| 项 | 内容 |
|---|---|
| 模块 | `src/agent.py` ↔ `src/llm_client.py` |
| 复现步骤 | 1) 启动本地假 OpenAI 服务端（严格按官方契约校验）<br>2) 让 Agent 执行任一工具（如 calculator）<br>3) 观察第二次请求 |
| 实际结果 | 第二轮请求体为 `tool_calls: [{"name": "calculator", "arguments": {"expression": "..."}, "id": "call_..."}]`，缺少 `type`，且 `arguments` 是对象而非 JSON 字符串 → 服务端 400 `invalid_request_error` |
| 预期结果 | `{"id": "...", "type": "function", "function": {"name": "...", "arguments": "<JSON 字符串>"}}` |
| 影响 | **任何真实 LLM 的多轮工具调用完全不可用**（原 60 个用例因用 MockLLM 绕过传输层而全部漏检） |
| 修复 | `LLMClient._normalize_messages` 统一转换为 OpenAI 线上格式，同时兼容"内部简化格式"与"原生格式"输入 |
| 回归 | IT-02 / IT-03 / IT-08 + 真实模型 `test_real_tool_call` |

### 🟠 严重级

#### D-02 todo 状态跨会话串台

| 项 | 内容 |
|---|---|
| 模块 | `src/tools/todo_list.py` ↔ `src/agent.py` |
| 复现步骤 | 窗口 1 添加待办 → 窗口 2 查询待办 |
| 实际结果 | 窗口 2 能看到窗口 1 的待办（`session_id` 未注入，全部落到 `_global`） |
| 预期结果 | 不同 session 的待办互相隔离 |
| 影响 | 直接违反"两个窗口互不影响"的硬性要求 |
| 修复 | 引入 `contextvars.CURRENT_SESSION_ID`，由 `ToolRegistry.execute(session_id=...)` 注入，不污染给 LLM 的 Schema |
| 回归 | IT-07（端到端隔离） |

#### D-03 思考过程被写入 assistant 正文进入上下文

| 项 | 内容 |
|---|---|
| 模块 | `src/agent.py` |
| 实际结果 | 工具调用轮次把 `thought` 存入 `assistant.content` 并进入后续 context |
| 预期结果 | 思考过程只进 trace，不进 context（README 声明与实现不一致） |
| 影响 | 上下文被推理文本污染，浪费 token，且与设计文档矛盾 |
| 修复 | 工具调用轮次 `content` 置空，`thought` 仅写 trace |
| 回归 | IT-02 断言、`test_normal_messages_preserved` |

#### D-06 中文 Windows 控制台（GBK）启动即崩溃

| 项 | 内容 |
|---|---|
| 模块 | `main.py` |
| 复现步骤 | `set PYTHONIOENCODING=gbk` 后运行 `python main.py` |
| 实际结果 | `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f916'` → 进程退出码 1 |
| 预期结果 | 保留中文正常显示，emoji 降级为 `?`，程序正常运行 |
| 影响 | cmd.exe 默认代码页 936 环境下**完全不可用** |
| 修复 | 启动时对 stdout/stderr 执行 `reconfigure(errors="replace")`，不改变编码 |
| 回归 | `test_cli_runs_under_gbk_console` |

#### D-09 幂运算无上限导致 CPU DoS

| 项 | 内容 |
|---|---|
| 模块 | `src/tools/calculator.py` |
| 复现步骤 | 调用 `calculator` 工具，参数 `expression = "9**9**9"` |
| 实际结果 | 进程长时间占满 CPU 不返回 |
| 预期结果 | 立即拒绝并返回受控错误 |
| 修复 | 指数上限 1000、底数上限 1e6 |
| 回归 | `test_pow_dos_guard` / `test_huge_base_guard` |

#### D-14 示例配置文件中存在真实格式密钥

| 项 | 内容 |
|---|---|
| 模块 | `.env.example` |
| 复现步骤 | 打开 `.env.example` 检查 `LLM_API_KEY` |
| 实际结果 | 值为 `sk-` 开头、约 35 字符的真实格式密钥，与 README "只放占位符" 的声明矛盾 |
| 预期结果 | 仅包含占位符 `sk-your-api-key-here`；真实密钥只存在于被忽略的 `.env` |
| 影响 | 提交 GitHub 即造成密钥泄露；`.gitignore` 只保护 `.env`，保护不到示例文件 |
| 修复 | 替换为占位符并补充注释；**真实密钥仍需在服务商控制台吊销/轮换** |
| 回归 | 人工核对 + `git check-ignore` 确认 `.env` 不会被跟踪 |

### 🟡 一般级

| ID | 模块 | 问题 | 修复 | 回归用例 |
|---|---|---|---|---|
| D-04 | `memory.py` | 轮次截断后首条为孤立 assistant（丢失其对应 user 提问），产生无归属上下文 | 按 user 索引切片，保证首条必为 user | `test_truncate_keeps_user_first` |
| D-05 | `memory.py` | 压缩生成 system 摘要后又插入主 system，出现两条 system | 合并为一条 | `test_compress_merges_system` |
| D-07 | `calculator.py` | `bool` 是 `int` 子类，`True + 1` 被算成 2 | 显式排除 bool | `test_bool_constant_rejected` |
| D-08 | `calculator.py` | `ast.parse` 抛出的 `ValueError`（如括号过多）未被捕获，裸异常外泄 | 捕获 `SyntaxError/ValueError/MemoryError` 统一转受控错误 | `test_deep_nesting` |
| D-10 | `calculator.py` | 超长链式表达式触发 `RecursionError` | 增加深度上限 200 + `RecursionError` 转换 | `test_extremely_long_expression_controlled` |
| D-11 | `llm_client.py` | 供应商不支持 `response_format=json_object` 时直接 400 失败 | 识别 400 后去掉该字段重试一次 | IT-11 |
| D-12 | `llm_client.py` | `content` 为数组 / `null` / 空串时解析不健壮 | 统一归一化（多模态数组、原生 tool_calls、空响应） | `TestLLMClientNormalization` 9 用例 |
| D-13 | `agent.py` | 达到 `max_steps` 时只写 trace、不写 `messages`，刷新后该轮回答消失 | 与其它返回路径一致，补写 assistant 消息 | `test_max_steps_exceeded` 新增断言 |
| D-15 | `web_server.py` | 未校验 `Host` 头，本机服务存在 DNS rebinding 风险 | 监听回环地址时仅允许 localhost/127.0.0.1/::1；显式对外监听时跳过 | `test_host_header_validation` |

---

## 5. 兼容性矩阵

| 维度 | 场景 | 结果 |
|---|---|---|
| OS | Windows 10/11（本机） | 通过 |
| Python | 3.14.6（实测） | 通过；源码要求 ≥3.10（PEP 604 联合类型） |
| 控制台编码 | UTF-8 (65001) | 通过 |
| 控制台编码 | GBK (936) | 通过（D-06 修复后） |
| 输入边界 | 空输入 / EOF(Ctrl+Z) / 超长输入 | 通过 |
| 模型供应商 | OpenAI 标准 JSON 输出 | 通过（假服务端严格校验） |
| 模型供应商 | 原生 `tool_calls` + `content=null` | 通过（IT-08） |
| 模型供应商 | 带 `reasoning_content`（Qwen） | 通过 |
| 模型供应商 | `content` 为数组（多模态） | 通过 |
| 模型供应商 | 不支持 `response_format` | 通过（自动降级） |
| 模型供应商 | Markdown 代码块包裹 JSON | 通过（IT-09） |
| 真实服务 | DashScope 兼容模式 + `qwen3.8-flash` | 通过（4/4 真实冒烟 + 5/5 评测） |
| 网络异常 | 上游 500 / 401 / 连接失败 | 通过（受控错误 + trace） |
| 浏览器 | Chromium 桌面 1440×900 | 通过（三栏、工具面板、重置、会话切换，无控制台错误） |
| 浏览器 | Chromium 移动 390×844 | 通过（抽屉可开合、无横向溢出、发送正常） |
| 浏览器 | 键盘 / 减少动态效果 / 焦点可见 | 通过（Enter 发送、Esc 关抽屉、`focus-visible`、`prefers-reduced-motion`） |

---

## 6. 质量评估

| 维度 | 评价 |
|---|---|
| 功能完整性 | 满足笔试题全部硬性要求（Loop、3 工具、Schema 注册、Session 隔离、Context 管理、异常、trace） |
| 可靠性 | 上游异常、工具异常、解析异常均受控；无裸异常外泄；无进程崩溃路径 |
| 安全性 | 无 `eval()` 任意执行；AST 白名单；幂运算 DoS 已封堵；API Key 不落代码 |
| 可维护性 | 模块职责单一，核心循环 60 行内；测试分层清晰 |
| 兼容性 | 双控制台编码、4 类供应商响应差异、真实服务均验证通过 |
| 覆盖率 | 94%（`sessions` 100%，`agent` / `llm_client` 93%） |

### 遗留项（非阻断，建议后续迭代）

1. `ContextManager.COMPRESS_THRESHOLD` 定义了但实际以 `MAX_CHARS` 判断，属冗余配置项。
2. 无 429/5xx 重试与退避，上游限流时直接失败（当前按"基本异常处理"要求，未实现重试）。
3. `SessionManager` / `todo_list` 为纯内存实现，无持久化与容量上限（与"最小可用"定位一致）。
4. CLI 与 Web 是两个独立进程，各自持有一份内存 session；同时使用时不共享对话状态。
5. Web 端的 Agent 执行由单把锁串行化，多用户并发时会排队（本机单人场景不受影响）。

---

## 7. 验收结论

- 阻断级缺陷 **1/1** 已修复并回归通过（D-01）。
- 严重级缺陷 **5/5** 已修复并回归通过（D-02、D-03、D-06、D-09、D-14）。
- 一般级缺陷 **9/9** 已修复并回归通过。
- 全量回归：**160 passed, 4 skipped, 0 failed**；真实环境冒烟 **4/4 passed**；真实模型评测 **5/5 passed**。
- 行覆盖率 **94%**。
- 前端：桌面与移动端浏览器用例全部通过，无控制台错误。

**结论：达到质量验收标准，可提交。**
