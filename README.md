# Meridian · 销售分析看板

基于 Next.js App Router 的销售数据可视化页面，包含 KPI 总览、时间/品类筛选、趋势与结构图表、订单明细和数据详情面板，并内置加载、空数据、异常与刷新失败四类状态。

## 快速开始

```bash
npm install

# 演示模式（无需后端，使用本地确定性数据）
# Windows PowerShell
$env:NEXT_PUBLIC_API_MOCK="1"; npm run dev
# macOS / Linux
NEXT_PUBLIC_API_MOCK=1 npm run dev
```

打开 http://localhost:3000 。

### 内置本地后端

项目自带一个零第三方依赖的 Node 后端（`server/index.mjs`），按下方接口契约提供数据：

```bash
# 终端 1
npm run backend     # http://localhost:8000
# 终端 2（不要设置 NEXT_PUBLIC_API_MOCK）
npm run dev         # http://localhost:3000
```

连接真实后端：

```bash
# 默认即为 http://localhost:8000/api/v1，无需额外配置
npm run dev
# 如需修改：
$env:NEXT_PUBLIC_API_BASE="http://localhost:8000/api/v1"; npm run dev
```

### 对接真实后端的检查项

1. 后端监听 `http://localhost:8000`，且存在 `GET /api/v1/analytics/dashboard`（契约见下文）。
2. 后端需允许前端来源的跨域请求（浏览器直连 8000 端口）：

```http
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET,OPTIONS
```

3. 先单独验证接口是否可用：

```powershell
Invoke-WebRequest "http://localhost:8000/api/v1/analytics/dashboard?start_date=2026-11-08&end_date=2026-11-14" -UseBasicParsing
```

4. 不要设置 `NEXT_PUBLIC_API_MOCK`，页面右上角应显示 `LIVE API`。若显示 `DEMO DATA`，说明仍在演示模式。
5. 若后端无法开启 CORS，可改用 Next.js `rewrites` 做同源代理，避免浏览器跨域。

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | Turbopack 启动开发服务器 |
| `npm run backend` | 启动本地后端（默认 8000，可用 `PORT` 覆盖） |
| `npm run build` | 生产构建（含类型检查与 ESLint） |
| `npm run start` | 启动生产服务器 |
| `npm run lint` | 单独执行 ESLint |

开发环境可直接验收页面状态（生产构建不会包含该逻辑）：

- `http://localhost:3000/?mock=empty` 空数据
- `http://localhost:3000/?mock=error` 接口异常

## 功能清单

- **KPI 总览**：总销售额、有效订单、销售件数、平均客单价，含环比与迷你趋势线。
- **交互筛选**：近 7/30/90 天、自定义日期区间、品类多选、关键词搜索（300ms 防抖）、一键重置。
- **趋势图**：销售额 / 订单量指标切换，30 天内按日、更长区间按周聚合，渐变面积 + 悬浮提示。
- **品类结构**：环形图 + 图例占比，点击扇区或图例即可按品类下钻。
- **订单明细**：日期 / 金额排序、前端分页、行选中，移动端自动折叠次要列。
- **详情面板**：订单金额、占区间营收比例、商品、渠道、地区、退款说明。
- **状态处理**：骨架屏、空状态、整页错误、刷新失败但仍保留旧数据的行内提示。
- **实时刷新**：每 15 秒同步一次，仅在标签页可见时触发；手动刷新可随时拉取。

## 目录结构

```
src/
├─ app/
│  ├─ globals.css          # 设计令牌、基础样式、动效
│  ├─ layout.tsx           # 根布局（Geist 字体）
│  ├─ page.tsx             # 首页入口
│  └─ icon.svg             # favicon
├─ components/dashboard/
│  ├─ DashboardView.tsx    # 页面编排与选中态
│  ├─ FilterBar.tsx        # 筛选控件
│  ├─ KpiCards.tsx         # KPI + 迷你趋势
│  ├─ TrendChart.tsx       # 折线图
│  ├─ CategoryPie.tsx      # 环形图与图例
│  ├─ DataTable.tsx        # 明细表（排序/分页）
│  ├─ DetailPanel.tsx      # 订单详情
│  ├─ StateViews.tsx       # 骨架屏/空/错误状态
│  ├─ Panel.tsx            # 统一卡片容器
│  ├─ Badges.tsx           # 品类、状态标签
│  ├─ icons.tsx            # 内联图标集
│  └─ chartSetup.ts        # Chart.js 按需注册
├─ hooks/
│  └─ useDashboardData.ts  # 请求、状态机、自动刷新
├─ lib/
│  ├─ types.ts             # 领域类型
│  ├─ api.ts               # 数据访问与错误映射
│  ├─ mock.ts              # 前端演示数据
│  ├─ format.ts            # 金额/日期格式化
│  ├─ theme.ts             # 品类配色
│  └─ cn.ts                # className 组合
└─ server/
   └─ index.mjs            # 内置本地后端（零依赖，端口 8000）
```

## 数据接口约定

页面只请求一个聚合接口，减少瀑布式请求：

```
GET {API_BASE}/analytics/dashboard
  ?start_date=2026-10-16
  &end_date=2026-11-14
  &category=电子产品        # 可重复，省略表示全部
  &q=耳机                  # 可选，商品名/订单号/地区/品类/渠道
```

响应支持 `{ data: {...} }`、`{ code, data }` 或裸对象；核心字段如下：

```jsonc
{
  "range": { "start": "2026-10-16", "end": "2026-11-14" },
  "summary": {
    "revenue":       { "value": 370937, "previous": 384531, "change": -0.035 },
    "orders":        { "value": 314,    "previous": 292,    "change": 0.075 },
    "units":         { "value": 453,    "previous": 414,    "change": 0.094 },
    "avgOrderValue": { "value": 1181.33, "previous": 1316.87, "change": -0.103 },
    "revenueSeries": [/* 最多 14 个点，用于迷你趋势 */],
    "ordersSeries": [],
    "unitsSeries": [],
    "avgOrderValueSeries": []
  },
  "trend": [
    { "date": "2026-10-16", "label": "10/16", "revenue": 10320, "orders": 9, "units": 13 }
  ],
  "categories": [
    { "category": "电子产品", "revenue": 141900, "orders": 120, "share": 0.382 }
  ],
  "records": [
    {
      "id": "SO-20261114-1636",
      "date": "2026-11-14",
      "productId": "P0021",
      "productName": "雪松香薰礼盒",
      "category": "日用品",
      "channel": "线下门店",
      "region": "西南",
      "quantity": 2,
      "unitPrice": 169,
      "amount": 338,
      "status": "已完成"
    }
  ],
  "totalRecords": 330,
  "updatedAt": "2026-11-14T00:30:00.000Z"
}
```

约定：

- `change` 为环比小数（`0.075` 表示 +7.5%），上期为 0 时返回 `null`。
- `trend` 的聚合粒度由服务端决定；前端只按返回顺序渲染。
- `records` 建议按日期倒序；`totalRecords` 为分页前总数。
- 退款订单不计入 KPI、趋势和品类统计，但仍会出现在明细中。
- 若后端字段不同，只需在 `src/lib/api.ts` 的 `unwrapPayload` 中做一次映射。

## 组件说明

| 组件 | 职责 | 关键 Props |
| --- | --- | --- |
| `DashboardView` | 页面编排、选中订单、移动端自动滚动到详情 | 无，内部使用 `useDashboardData` |
| `FilterBar` | 时间预设/自定义日期、品类多选、搜索防抖、刷新与重置 | `filters`、`onPreset`、`onCustomRange`、`onToggleCategory`、`onQueryChange`、`onRefresh` |
| `KpiCards` | 4 个指标卡与环比、迷你趋势 | `summary: KpiSummary`、`refreshing?` |
| `TrendChart` | 折线图与指标切换 | `trend`、`metric`、`onMetricChange` |
| `CategoryPie` | 环形图、可点击图例 | `slices`、`selected`、`onToggleCategory` |
| `DataTable` | 排序、分页、行选中 | `records`、`selectedId`、`onSelect`、`filterSignature` |
| `DetailPanel` | 订单详情与占区间营收比例 | `record`、`totalRevenue`、`totalRecords`、`onClose` |
| `StateViews` | 骨架屏、空状态、错误态、行内错误 | `onReset` / `message`、`onRetry` |
| `Panel` | 统一卡片容器 | `title`、`subtitle`、`action`、`children` |

全部领域类型集中在 `src/lib/types.ts`。新增品类时，同步修改 `CATEGORIES` 与 `src/lib/theme.ts` 中的配色映射即可。

## 状态与刷新机制

`useDashboardData` 统一管理筛选条件、请求与状态机：

1. 每次请求携带自增序号，只有最新请求能写入状态，避免慢请求覆盖新结果。
2. 新请求会中止上一个请求（`AbortController`），连续切换筛选不会堆积网络开销。
3. 首次加载展示骨架屏；刷新时保留旧数据，仅在顶部显示「同步中」，避免布局跳动。
4. 刷新失败但已有数据时，展示行内错误提示并保留上一份数据，同时可手动重试。
5. 每 15 秒自动刷新一次，且仅在 `document.visibilityState === "visible"` 时执行。

## 响应式与可访问性

- 断点：`sm` 双列 KPI，`md/lg` 图表与表格分栏，`lg` 详情面板吸顶。
- 移动端隐藏订单号、渠道、数量等次要列，保留日期、商品、金额、状态。
- 表格行支持 `Enter` / 空格键选中；筛选按钮使用 `aria-pressed`；图标均带 `aria-label` 或隐藏。
- 图表容器固定高度并 `maintainAspectRatio: false`，避免移动端高度塌陷。
- 支持 `prefers-reduced-motion`。

## 自测记录

- `npm run build`：通过（Next.js 15.5.29 + Turbopack，静态预渲染 4 个页面）。
- `npm run lint`：通过，0 error / 0 warning。
- Chrome 无头模式（Playwright）验证：
  - 1440×900：4 张 KPI、2 个图表、每页 8 行、无横向溢出、无控制台错误。
  - 390×844：KPI 单列、筛选栏正常换行、表格无横向溢出、选中行后详情自动滚动到可视区。
  - 交互：指标切换、品类下钻、搜索（含防抖）、重置、日期预设、行选中、分页均通过。
  - 状态：`?mock=empty` 空状态、`?mock=error` 错误状态与重试、首屏骨架屏均验证通过。
- 真实 HTTP 联调（内置后端）：请求携带正确的 `start_date` / `end_date` / `category` / `q` 参数，KPI、图表与明细均由接口数据渲染；后端返回 503 时保留旧数据并提示，重载后展示整页错误与重试。

## 备注

- 内置后端的 1661 条订单在启动时由固定种子生成并驻留内存，不写数据库；重启服务后数据会重新生成。
- 当前明细采用前端分页（每页 8 条），面向千级数据；若单区间记录量很大，建议后端提供分页并把 `page/pageSize` 提升为受控参数。
- 演示数据由固定种子生成，覆盖最近 180 天，同一天内刷新结果稳定，便于视觉回归。
- Chart.js 采用按需注册（`chartSetup.ts`），首屏 JS 约 197KB。
