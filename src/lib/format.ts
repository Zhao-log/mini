/**
 * 展示层格式化工具。
 *
 * 约定：
 * - 金额一律使用人民币符号，整数部分加千分位；
 * - 不依赖运行环境的默认 locale，显式指定 zh-CN，避免服务端/客户端渲染差异；
 * - 日期字符串按「本地日期」解析，绕开 new Date("yyyy-MM-dd") 的 UTC 偏移问题。
 */

const numberFormatter = new Intl.NumberFormat("zh-CN");

const currencyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 0,
});

const decimalCurrencyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** ¥1,234,567 */
export function formatCurrency(value: number): string {
  return currencyFormatter.format(Math.round(value));
}

/** ¥1,234.50 —— 用于客单价、明细行等需要精度的场景 */
export function formatCurrencyPrecise(value: number): string {
  return decimalCurrencyFormatter.format(value);
}

/**
 * 大额金额的中文紧凑写法：1.28万 / 3,204
 * 仅用于 KPI 主数字，避免长数字撑破卡片。
 */
export function formatCompactCurrency(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 100_000_000) return `¥${(value / 100_000_000).toFixed(2)}亿`;
  if (abs >= 10_000) return `¥${(value / 10_000).toFixed(abs >= 1_000_000 ? 0 : 2)}万`;
  return `¥${numberFormatter.format(Math.round(value))}`;
}

/** 1,234 */
export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

/** 12.4% —— 传入 0.124 */
export function formatRatio(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** +12.4% / -3.1% / — */
export function formatSignedPercent(value: number | null, digits = 1): string {
  if (value === null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
}

/** 解析 yyyy-MM-dd 为本地日期，避免时区偏移 */
export function parseISODate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, (month ?? 1) - 1, day ?? 1);
}

/** Date → yyyy-MM-dd */
export function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** 在指定日期上增减天数，返回新的 Date */
export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** 两个 ISO 日期之间的天数（含首尾） */
export function daysBetween(startISO: string, endISO: string): number {
  const start = parseISODate(startISO).getTime();
  const end = parseISODate(endISO).getTime();
  return Math.max(1, Math.round((end - start) / 86_400_000) + 1);
}

/** 11/14 */
export function formatAxisDate(iso: string): string {
  const date = parseISODate(iso);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

/** 2026年11月14日 */
export function formatLongDate(iso: string): string {
  const date = parseISODate(iso);
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

/** 2026年11月14日 09:32 */
export function formatDateTime(date: Date): string {
  const hh = `${date.getHours()}`.padStart(2, "0");
  const mm = `${date.getMinutes()}`.padStart(2, "0");
  return `${formatLongDate(toISODate(date))} ${hh}:${mm}`;
}

/** 相对时间：刚刚 / 32 秒前 / 5 分钟前 */
export function formatRelativeTime(date: Date, now: number): string {
  const diff = Math.max(0, Math.round((now - date.getTime()) / 1000));
  if (diff < 5) return "刚刚";
  if (diff < 60) return `${diff} 秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  return `${Math.floor(diff / 3600)} 小时前`;
}
