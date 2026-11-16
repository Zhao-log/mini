/**
 * 销售分析看板 —— 全局领域类型定义
 *
 * 该文件只存放「跨层共享」的类型，组件内部状态类型请就近定义。
 * 后端接口结构调整时，优先修改此处，再由 TypeScript 提示需要同步的位置。
 */

/** 平台支持的五类商品品类（与后端枚举保持一致） */
export const CATEGORIES = ["电子产品", "运动用品", "家电", "家具", "日用品"] as const;

export type Category = (typeof CATEGORIES)[number];

/** 订单状态：退款订单不计入营收与订单量统计 */
export type SalesStatus = "已完成" | "待发货" | "已退款";

export type SalesChannel = "线上商城" | "线下门店" | "分销渠道";

/** 一条销售记录 = 一个订单行 */
export interface SalesRecord {
  id: string;
  /** 交易日期，格式 yyyy-MM-dd（本地时区，不含时间） */
  date: string;
  productId: string;
  productName: string;
  category: Category;
  channel: SalesChannel;
  region: string;
  quantity: number;
  unitPrice: number;
  amount: number;
  status: SalesStatus;
}

/** 趋势图可切换的指标 */
export type MetricKey = "revenue" | "orders";

/** 时间范围预设，custom 表示用户自定义区间 */
export type RangePreset = 7 | 30 | 90 | "custom";

export interface DateRange {
  /** yyyy-MM-dd */
  start: string;
  /** yyyy-MM-dd */
  end: string;
}

/** 页面上全部可交互筛选条件的集合 */
export interface DashboardFilters extends DateRange {
  preset: RangePreset;
  /** 空数组代表「全部品类」 */
  categories: Category[];
  /** 商品名 / 订单号 / 地区关键词 */
  query: string;
  /** 仅影响图表展示，不触发请求 */
  metric: MetricKey;
}

/** 单个 KPI 的数值与环比 */
export interface KpiMetric {
  value: number;
  previous: number;
  /** 环比变化率，0.12 表示 +12%；上期为 0 时为 null */
  change: number | null;
}

export interface KpiSummary {
  revenue: KpiMetric;
  orders: KpiMetric;
  units: KpiMetric;
  avgOrderValue: KpiMetric;
  /** 迷你折线图数据（与当前区间等长，最多 14 个点） */
  revenueSeries: number[];
  ordersSeries: number[];
  unitsSeries: number[];
  avgOrderValueSeries: number[];
}

export interface TrendPoint {
  /** yyyy-MM-dd（周维度时为桶的起始日） */
  date: string;
  /** 坐标轴展示文案，如 11/14 */
  label: string;
  revenue: number;
  orders: number;
  /** 销售件数，部分后端可能不返回，前端按 0 处理 */
  units?: number;
}

export interface CategorySlice {
  category: Category;
  revenue: number;
  orders: number;
  /** 占总营收比例 0~1 */
  share: number;
}

/** 看板接口的完整响应体 */
export interface DashboardData {
  range: DateRange;
  summary: KpiSummary;
  trend: TrendPoint[];
  categories: CategorySlice[];
  /** 当前筛选条件下的明细记录，按日期倒序 */
  records: SalesRecord[];
  /** 满足筛选条件的总记录数（分页前） */
  totalRecords: number;
  /** 服务端数据生成时间，ISO 字符串 */
  updatedAt: string;
}

/** 请求状态机 */
export type LoadStatus = "loading" | "refreshing" | "success" | "error";
