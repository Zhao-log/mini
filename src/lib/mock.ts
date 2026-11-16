import {
  CATEGORIES,
  type Category,
  type CategorySlice,
  type DashboardData,
  type DashboardFilters,
  type DateRange,
  type KpiMetric,
  type SalesChannel,
  type SalesRecord,
  type SalesStatus,
  type TrendPoint,
} from "@/lib/types";
import { addDays, daysBetween, formatAxisDate, parseISODate, toISODate } from "@/lib/format";

/**
 * 本地 Mock 数据源。
 *
 * 后端未启动时通过 `NEXT_PUBLIC_API_MOCK=1` 启用，用于演示与自测。
 * 数据由固定种子生成，同一天内多次刷新结果一致，便于 UI 回归对比。
 */

const PRODUCT_CATALOG: Array<{ name: string; category: Category; price: number }> = [
  { name: "智能降噪耳机", category: "电子产品", price: 899 },
  { name: "便携投影仪", category: "电子产品", price: 2499 },
  { name: "运动手环 Pro", category: "电子产品", price: 399 },
  { name: "无线充电底座", category: "电子产品", price: 199 },
  { name: "27 英寸 4K 显示器", category: "电子产品", price: 1899 },
  { name: "轻量缓震跑步鞋", category: "运动用品", price: 469 },
  { name: "天然橡胶瑜伽垫", category: "运动用品", price: 159 },
  { name: "三层户外冲锋衣", category: "运动用品", price: 899 },
  { name: "可调节哑铃组", category: "运动用品", price: 699 },
  { name: "骑行防护头盔", category: "运动用品", price: 329 },
  { name: "空气炸锅 5L", category: "家电", price: 499 },
  { name: "一级能效变频空调", category: "家电", price: 3299 },
  { name: "扫拖一体机器人", category: "家电", price: 2199 },
  { name: "静音破壁机", category: "家电", price: 899 },
  { name: "恒温电热水壶", category: "家电", price: 199 },
  { name: "人体工学办公椅", category: "家具", price: 1299 },
  { name: "实木升降书桌", category: "家具", price: 1599 },
  { name: "模块化布艺沙发", category: "家具", price: 3299 },
  { name: "原木五斗柜", category: "家具", price: 899 },
  { name: "黄铜落地阅读灯", category: "家具", price: 399 },
  { name: "雪松香薰礼盒", category: "日用品", price: 169 },
  { name: "折叠收纳箱三件套", category: "日用品", price: 129 },
  { name: "长绒棉浴巾", category: "日用品", price: 89 },
  { name: "不锈钢厨房刀具套装", category: "日用品", price: 299 },
  { name: "真空保温杯 500ml", category: "日用品", price: 139 },
];

const CATEGORY_WEIGHTS: Record<Category, number> = {
  电子产品: 0.3,
  日用品: 0.26,
  运动用品: 0.18,
  家电: 0.14,
  家具: 0.12,
};

const REGIONS = ["华东", "华南", "华北", "西南", "华中", "东北"] as const;

const CHANNELS: Array<{ value: SalesChannel; weight: number }> = [
  { value: "线上商城", weight: 0.6 },
  { value: "线下门店", weight: 0.25 },
  { value: "分销渠道", weight: 0.15 },
];

const STATUS_WEIGHTS: Array<{ value: SalesStatus; weight: number }> = [
  { value: "已完成", weight: 0.88 },
  { value: "待发货", weight: 0.07 },
  { value: "已退款", weight: 0.05 },
];

/** mulberry32：轻量确定性伪随机数生成器 */
function createRandom(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 按权重从数组中取一项 */
function pickWeighted<T>(items: Array<{ value: T; weight: number }>, random: () => number): T {
  const total = items.reduce((sum, item) => sum + item.weight, 0);
  let cursor = random() * total;
  for (const item of items) {
    cursor -= item.weight;
    if (cursor <= 0) return item.value;
  }
  return items[items.length - 1].value;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

/** 生成最近 180 天的历史订单（模块级缓存，避免每次请求重复构造） */
const HISTORY_DAYS = 180;

function generateHistory(): SalesRecord[] {
  const random = createRandom(20261114);
  const today = new Date();
  const records: SalesRecord[] = [];
  let sequence = 0;

  for (let offset = HISTORY_DAYS - 1; offset >= 0; offset -= 1) {
    const date = addDays(today, -offset);
    const iso = toISODate(date);
    const weekday = date.getDay();
    const weekendFactor = weekday === 0 || weekday === 6 ? 1.28 : 1;
    // 缓慢增长的业务趋势，让 30 天环比有正有负
    const growth = 0.78 + (HISTORY_DAYS - offset) / HISTORY_DAYS * 0.42;
    const dailyOrders = Math.round((6 + random() * 5) * weekendFactor * growth);

    for (let i = 0; i < dailyOrders; i += 1) {
      const category = pickWeighted(
        CATEGORIES.map((value) => ({ value, weight: CATEGORY_WEIGHTS[value] })),
        random,
      );
      const candidates = PRODUCT_CATALOG.filter((product) => product.category === category);
      const product = candidates[Math.floor(random() * candidates.length)];
      const quantity = random() < 0.65 ? 1 : random() < 0.75 ? 2 : 3;
      const unitPrice = product.price;
      sequence += 1;

      records.push({
        id: `SO-${iso.replaceAll("-", "")}-${`${sequence % 10000}`.padStart(4, "0")}`,
        date: iso,
        productId: `P${PRODUCT_CATALOG.indexOf(product) + 1}`.padStart(4, "0"),
        productName: product.name,
        category,
        channel: pickWeighted(CHANNELS, random),
        region: REGIONS[Math.floor(random() * REGIONS.length)],
        quantity,
        unitPrice,
        amount: round2(unitPrice * quantity),
        status: pickWeighted(STATUS_WEIGHTS, random),
      });
    }
  }

  return records.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

const HISTORY = generateHistory();

/** 退款订单不计入营收、订单量与销量 */
function isEffective(record: SalesRecord): boolean {
  return record.status !== "已退款";
}

function filterRecords(
  records: SalesRecord[],
  range: DateRange,
  categories: Category[],
  query: string,
): SalesRecord[] {
  const keyword = query.trim().toLowerCase();
  return records.filter((record) => {
    if (record.date < range.start || record.date > range.end) return false;
    if (categories.length > 0 && !categories.includes(record.category)) return false;
    if (!keyword) return true;
    return (
      record.id.toLowerCase().includes(keyword) ||
      record.productName.toLowerCase().includes(keyword) ||
      record.region.toLowerCase().includes(keyword) ||
      record.category.includes(keyword) ||
      record.channel.includes(keyword)
    );
  });
}

function aggregate(records: SalesRecord[]) {
  let revenue = 0;
  let orders = 0;
  let units = 0;
  for (const record of records) {
    if (!isEffective(record)) continue;
    revenue += record.amount;
    orders += 1;
    units += record.quantity;
  }
  return { revenue: round2(revenue), orders, units };
}

function toMetric(current: number, previous: number): KpiMetric {
  return {
    value: current,
    previous,
    change: previous > 0 ? (current - previous) / previous : null,
  };
}

/** 将区间拆成连续的每日/每周桶，并对缺失日期补零 */
function buildTrend(records: SalesRecord[], range: DateRange): TrendPoint[] {
  const span = daysBetween(range.start, range.end);
  const bucketSize = span <= 31 ? 1 : 7;
  const start = parseISODate(range.start);
  const buckets: TrendPoint[] = [];

  for (let cursor = 0; cursor < span; cursor += bucketSize) {
    const bucketStart = addDays(start, cursor);
    buckets.push({
      date: toISODate(bucketStart),
      label: formatAxisDate(toISODate(bucketStart)),
      revenue: 0,
      orders: 0,
    });
  }

  for (const record of records) {
    if (!isEffective(record)) continue;
    const dayIndex = Math.max(0, daysBetween(range.start, record.date) - 1);
    const bucketIndex = Math.min(buckets.length - 1, Math.floor(dayIndex / bucketSize));
    const bucket = buckets[bucketIndex];
    bucket.revenue = round2(bucket.revenue + record.amount);
    bucket.orders += 1;
    bucket.units = (bucket.units ?? 0) + record.quantity;
  }

  return buckets;
}

function buildCategorySlices(records: SalesRecord[]): CategorySlice[] {
  const totals = new Map<Category, { revenue: number; orders: number }>();
  for (const category of CATEGORIES) totals.set(category, { revenue: 0, orders: 0 });

  for (const record of records) {
    if (!isEffective(record)) continue;
    const entry = totals.get(record.category);
    if (!entry) continue;
    entry.revenue += record.amount;
    entry.orders += 1;
  }

  const totalRevenue = [...totals.values()].reduce((sum, item) => sum + item.revenue, 0);

  return [...totals.entries()]
    .map(([category, item]) => ({
      category,
      revenue: round2(item.revenue),
      orders: item.orders,
      share: totalRevenue > 0 ? item.revenue / totalRevenue : 0,
    }))
    .filter((slice) => slice.revenue > 0)
    .sort((a, b) => b.revenue - a.revenue);
}

/** 计算等长的上一个统计周期 */
function previousRange(range: DateRange): DateRange {
  const span = daysBetween(range.start, range.end);
  const previousEnd = addDays(parseISODate(range.start), -1);
  const previousStart = addDays(previousEnd, -(span - 1));
  return { start: toISODate(previousStart), end: toISODate(previousEnd) };
}

export function buildMockDashboard(filters: DashboardFilters, now = new Date()): DashboardData {
  const range: DateRange = { start: filters.start, end: filters.end };
  const currentRecords = filterRecords(HISTORY, range, filters.categories, filters.query);
  const previousRecords = filterRecords(HISTORY, previousRange(range), filters.categories, filters.query);

  const current = aggregate(currentRecords);
  const previous = aggregate(previousRecords);
  const trend = buildTrend(currentRecords, range);

  return {
    range,
    summary: {
      revenue: toMetric(current.revenue, previous.revenue),
      orders: toMetric(current.orders, previous.orders),
      units: toMetric(current.units, previous.units),
      avgOrderValue: toMetric(
        current.orders > 0 ? round2(current.revenue / current.orders) : 0,
        previous.orders > 0 ? round2(previous.revenue / previous.orders) : 0,
      ),
      revenueSeries: trend.slice(-14).map((point) => point.revenue),
      ordersSeries: trend.slice(-14).map((point) => point.orders),
      unitsSeries: trend.slice(-14).map((point) => point.units ?? 0),
      avgOrderValueSeries: trend
        .slice(-14)
        .map((point) => (point.orders > 0 ? round2(point.revenue / point.orders) : 0)),
    },
    trend,
    categories: buildCategorySlices(currentRecords),
    records: currentRecords,
    totalRecords: currentRecords.length,
    updatedAt: now.toISOString(),
  };
}

/** 供「空状态」自测使用的空数据集 */
export function buildEmptyDashboard(filters: DashboardFilters, now = new Date()): DashboardData {
  const emptyMetric: KpiMetric = { value: 0, previous: 0, change: null };
  return {
    range: { start: filters.start, end: filters.end },
    summary: {
      revenue: emptyMetric,
      orders: emptyMetric,
      units: emptyMetric,
      avgOrderValue: emptyMetric,
      revenueSeries: [],
      ordersSeries: [],
      unitsSeries: [],
      avgOrderValueSeries: [],
    },
    trend: [],
    categories: [],
    records: [],
    totalRecords: 0,
    updatedAt: now.toISOString(),
  };
}
