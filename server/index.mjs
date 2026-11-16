/**
 * Meridian 销售分析看板 —— 本地后端服务
 *
 * 零第三方依赖，使用 Node 内置 http 模块实现。
 * 启动：npm run backend（默认监听 8000，可用 PORT 覆盖）
 *
 * 接口：
 *   GET /health
 *   GET /api/v1/analytics/dashboard?start_date&end_date&category&q
 *
 * 数据由固定种子生成，进程启动后驻留内存；重启服务不会改变当日结果。
 */
import http from "node:http";

const PORT = Number(process.env.PORT || 8000);
const HISTORY_DAYS = 180;

const CATEGORIES = ["电子产品", "运动用品", "家电", "家具", "日用品"];

const PRODUCTS = [
  ["电子产品", "智能降噪耳机", 899],
  ["电子产品", "便携投影仪", 2499],
  ["电子产品", "运动手环 Pro", 399],
  ["电子产品", "无线充电底座", 199],
  ["电子产品", "27 英寸 4K 显示器", 1899],
  ["运动用品", "轻量缓震跑步鞋", 469],
  ["运动用品", "天然橡胶瑜伽垫", 159],
  ["运动用品", "三层户外冲锋衣", 899],
  ["运动用品", "可调节哑铃组", 699],
  ["运动用品", "骑行防护头盔", 329],
  ["家电", "空气炸锅 5L", 499],
  ["家电", "一级能效变频空调", 3299],
  ["家电", "扫拖一体机器人", 2199],
  ["家电", "静音破壁机", 899],
  ["家电", "恒温电热水壶", 199],
  ["家具", "人体工学办公椅", 1299],
  ["家具", "实木升降书桌", 1599],
  ["家具", "模块化布艺沙发", 3299],
  ["家具", "原木五斗柜", 899],
  ["家具", "黄铜落地阅读灯", 399],
  ["日用品", "雪松香薰礼盒", 169],
  ["日用品", "折叠收纳箱三件套", 129],
  ["日用品", "长绒棉浴巾", 89],
  ["日用品", "不锈钢厨房刀具套装", 299],
  ["日用品", "真空保温杯 500ml", 139],
];

const CATEGORY_WEIGHTS = {
  电子产品: 0.3,
  日用品: 0.26,
  运动用品: 0.18,
  家电: 0.14,
  家具: 0.12,
};

const REGIONS = ["华东", "华南", "华北", "西南", "华中", "东北"];
const CHANNELS = ["线上商城", "线下门店", "分销渠道"];

/** mulberry32：确定性伪随机数 */
function createRandom(seed) {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick(items, random) {
  return items[Math.floor(random() * items.length)];
}

function pickCategory(random) {
  let cursor = random();
  for (const category of CATEGORIES) {
    cursor -= CATEGORY_WEIGHTS[category];
    if (cursor <= 0) return category;
  }
  return CATEGORIES[CATEGORIES.length - 1];
}

function toISODate(date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function parseISODate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

function daysBetween(startISO, endISO) {
  const start = parseISODate(startISO).getTime();
  const end = parseISODate(endISO).getTime();
  return Math.max(1, Math.round((end - start) / 86400000) + 1);
}

/** 生成历史订单（启动时执行一次） */
function generateHistory() {
  const random = createRandom(20261114);
  const today = new Date();
  const records = [];
  let sequence = 0;

  for (let offset = HISTORY_DAYS - 1; offset >= 0; offset -= 1) {
    const date = addDays(today, -offset);
    const iso = toISODate(date);
    const weekday = date.getDay();
    const weekend = weekday === 0 || weekday === 6 ? 1.28 : 1;
    const growth = 0.78 + ((HISTORY_DAYS - offset) / HISTORY_DAYS) * 0.42;
    const count = Math.round((6 + random() * 5) * weekend * growth);

    for (let i = 0; i < count; i += 1) {
      const category = pickCategory(random);
      const candidates = PRODUCTS.filter((product) => product[0] === category);
      const product = pick(candidates, random);
      const quantity = random() < 0.65 ? 1 : random() < 0.75 ? 2 : 3;
      const unitPrice = product[2];
      const status = random() < 0.05 ? "已退款" : random() < 0.07 ? "待发货" : "已完成";
      sequence += 1;

      records.push({
        id: `SO-${iso.replaceAll("-", "")}-${String(sequence % 10000).padStart(4, "0")}`,
        date: iso,
        productId: `P${String(PRODUCTS.indexOf(product) + 1).padStart(4, "0")}`,
        productName: product[1],
        category,
        channel: pick(CHANNELS, random),
        region: pick(REGIONS, random),
        quantity,
        unitPrice,
        amount: Math.round(unitPrice * quantity * 100) / 100,
        status,
      });
    }
  }

  return records.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

const HISTORY = generateHistory();

function isEffective(record) {
  return record.status !== "已退款";
}

function selectRecords(range, categories, query) {
  const keyword = (query || "").trim().toLowerCase();
  return HISTORY.filter((record) => {
    if (record.date < range.start || record.date > range.end) return false;
    if (categories.length && !categories.includes(record.category)) return false;
    if (!keyword) return true;
    return (
      record.id.toLowerCase().includes(keyword) ||
      record.productName.toLowerCase().includes(keyword) ||
      record.region.includes(keyword) ||
      record.category.includes(keyword) ||
      record.channel.includes(keyword)
    );
  });
}

function aggregate(records) {
  let revenue = 0;
  let orders = 0;
  let units = 0;
  for (const record of records) {
    if (!isEffective(record)) continue;
    revenue += record.amount;
    orders += 1;
    units += record.quantity;
  }
  return { revenue: Math.round(revenue * 100) / 100, orders, units };
}

function metric(current, previous) {
  return {
    value: current,
    previous,
    change: previous > 0 ? (current - previous) / previous : null,
  };
}

function buildTrend(records, range) {
  const span = daysBetween(range.start, range.end);
  const step = span <= 31 ? 1 : 7;
  const start = parseISODate(range.start);
  const buckets = [];

  for (let cursor = 0; cursor < span; cursor += step) {
    const date = addDays(start, cursor);
    const iso = toISODate(date);
    buckets.push({
      date: iso,
      label: `${date.getMonth() + 1}/${date.getDate()}`,
      revenue: 0,
      orders: 0,
      units: 0,
    });
  }

  for (const record of records) {
    if (!isEffective(record)) continue;
    const dayIndex = Math.max(0, daysBetween(range.start, record.date) - 1);
    const bucket = buckets[Math.min(buckets.length - 1, Math.floor(dayIndex / step))];
    bucket.revenue = Math.round((bucket.revenue + record.amount) * 100) / 100;
    bucket.orders += 1;
    bucket.units += record.quantity;
  }

  return buckets;
}

function buildCategories(records) {
  const totals = new Map(CATEGORIES.map((category) => [category, { revenue: 0, orders: 0 }]));
  for (const record of records) {
    if (!isEffective(record)) continue;
    const entry = totals.get(record.category);
    entry.revenue += record.amount;
    entry.orders += 1;
  }
  const total = [...totals.values()].reduce((sum, item) => sum + item.revenue, 0);
  return [...totals.entries()]
    .filter(([, item]) => item.revenue > 0)
    .map(([category, item]) => ({
      category,
      revenue: Math.round(item.revenue * 100) / 100,
      orders: item.orders,
      share: total > 0 ? item.revenue / total : 0,
    }))
    .sort((a, b) => b.revenue - a.revenue);
}

function previousRange(range) {
  const span = daysBetween(range.start, range.end);
  const end = addDays(parseISODate(range.start), -1);
  const start = addDays(end, -(span - 1));
  return { start: toISODate(start), end: toISODate(end) };
}

function buildDashboard(query) {
  const today = toISODate(new Date());
  const end = query.get("end_date") || today;
  const start = query.get("start_date") || toISODate(addDays(parseISODate(end), -29));

  if (!parseISODate(start) || !parseISODate(end)) {
    return { error: "start_date / end_date 需为合法的 yyyy-MM-dd 格式" };
  }
  if (start > end) {
    return { error: "start_date 不能晚于 end_date" };
  }

  const categories = query
    .getAll("category")
    .flatMap((value) => value.split(","))
    .map((value) => value.trim())
    .filter((value) => CATEGORIES.includes(value));
  const keyword = query.get("q") || "";
  const range = { start, end };

  const current = selectRecords(range, categories, keyword);
  const previous = selectRecords(previousRange(range), categories, keyword);
  const currentTotals = aggregate(current);
  const previousTotals = aggregate(previous);
  const trend = buildTrend(current, range);

  return {
    data: {
      range,
      summary: {
        revenue: metric(currentTotals.revenue, previousTotals.revenue),
        orders: metric(currentTotals.orders, previousTotals.orders),
        units: metric(currentTotals.units, previousTotals.units),
        avgOrderValue: metric(
          currentTotals.orders ? Math.round((currentTotals.revenue / currentTotals.orders) * 100) / 100 : 0,
          previousTotals.orders ? Math.round((previousTotals.revenue / previousTotals.orders) * 100) / 100 : 0,
        ),
        revenueSeries: trend.slice(-14).map((point) => point.revenue),
        ordersSeries: trend.slice(-14).map((point) => point.orders),
        unitsSeries: trend.slice(-14).map((point) => point.units),
        avgOrderValueSeries: trend
          .slice(-14)
          .map((point) => (point.orders ? Math.round((point.revenue / point.orders) * 100) / 100 : 0)),
      },
      trend,
      categories: buildCategories(current),
      records: current,
      totalRecords: current.length,
      updatedAt: new Date().toISOString(),
    },
  };
}

function send(res, status, payload, origin) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET,OPTIONS",
    "Access-Control-Allow-Headers": "Accept,Content-Type",
    Vary: "Origin",
    "Cache-Control": "no-store",
  });
  res.end(JSON.stringify(payload));
}

const server = http.createServer((req, res) => {
  const origin = req.headers.origin || "*";
  const url = new URL(req.url, `http://localhost:${PORT}`);
  console.log(`${new Date().toISOString()} ${req.method} ${url.pathname}${url.search}`);

  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET,OPTIONS",
      "Access-Control-Allow-Headers": "Accept,Content-Type",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin",
    });
    res.end();
    return;
  }

  if (req.method !== "GET") {
    send(res, 405, { message: "Method Not Allowed" }, origin);
    return;
  }

  if (url.pathname === "/health") {
    send(res, 200, { status: "ok", orders: HISTORY.length, uptime: Math.round(process.uptime()) }, origin);
    return;
  }

  if (url.pathname === "/api/v1/analytics/dashboard") {
    const result = buildDashboard(url.searchParams);
    if (result.error) {
      send(res, 400, { message: result.error }, origin);
      return;
    }
    send(res, 200, result, origin);
    return;
  }

  send(res, 404, { message: "Not Found" }, origin);
});

server.listen(PORT, () => {
  console.log(`[meridian-api] listening on http://localhost:${PORT}`);
  console.log(`[meridian-api] ${HISTORY.length} orders in memory, ${HISTORY_DAYS} days history`);
});

function shutdown(signal) {
  console.log(`[meridian-api] ${signal} received, shutting down`);
  server.close(() => process.exit(0));
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
