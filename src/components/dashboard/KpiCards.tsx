"use client";

import { useId } from "react";
import { KpiMetric, KpiSummary } from "@/lib/types";
import { formatCompactCurrency, formatCurrencyPrecise, formatNumber, formatSignedPercent } from "@/lib/format";
import { cn } from "@/lib/cn";

interface SparklineProps {
  values: number[];
  stroke: string;
  fill: string;
  className?: string;
}

/**
 * KPI 卡底部的迷你趋势线。
 * 使用 Catmull-Rom 思路的平滑折线（贝塞尔控制点取相邻点中位），
 * 无需额外图表实例，单个 SVG 即可完成，几乎零渲染成本。
 */
function Sparkline({ values, stroke, fill, className }: SparklineProps) {
  const gradientId = `spark-${useId().replace(/:/g, "")}`;
  if (values.length < 2) return <div className={cn("h-10", className)} />;

  const width = 180;
  const height = 44;
  const padding = 3;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;

  const points = values.map((value, index) => {
    const x = padding + (index / (values.length - 1)) * (width - padding * 2);
    const y = height - padding - ((value - min) / span) * (height - padding * 2);
    return [x, y] as const;
  });

  let line = `M ${points[0][0].toFixed(1)},${points[0][1].toFixed(1)}`;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const midX = (previous[0] + current[0]) / 2;
    line += ` C ${midX.toFixed(1)},${previous[1].toFixed(1)} ${midX.toFixed(1)},${current[1].toFixed(1)} ${current[0].toFixed(1)},${current[1].toFixed(1)}`;
  }
  const area = `${line} L ${points[points.length - 1][0].toFixed(1)},${height} L ${points[0][0].toFixed(1)},${height} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn("h-10 w-full", className)}
      role="img"
      aria-label="区间内趋势走势"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={fill} stopOpacity="0.55" />
          <stop offset="100%" stopColor={fill} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

interface DeltaBadgeProps {
  metric: KpiMetric;
  tone?: "light" | "dark";
}

function DeltaBadge({ metric, tone = "light" }: DeltaBadgeProps) {
  if (metric.change === null) {
    return <span className="text-[11px] text-muted">暂无对比数据</span>;
  }
  const up = metric.change >= 0;
  const palette =
    tone === "dark"
      ? up
        ? "bg-white/10 text-[#a7e3c0]"
        : "bg-white/10 text-[#f2b6a7]"
      : up
        ? "bg-forest-soft text-forest"
        : "bg-danger-soft text-danger";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-[3px] text-[11px] font-semibold tnum",
        palette,
      )}
    >
      <svg viewBox="0 0 10 10" className={cn("size-2.5", !up && "rotate-180")} aria-hidden="true">
        <path d="M5 1.5 8.6 7H1.4L5 1.5Z" fill="currentColor" />
      </svg>
      {formatSignedPercent(metric.change)}
    </span>
  );
}

interface KpiCardsProps {
  summary: KpiSummary;
  /** 刷新中时轻微降低透明度，提示数据可能滞后 */
  refreshing?: boolean;
}

/**
 * 核心指标区：1 个主指标（深色）+ 3 个辅助指标。
 * 主卡使用深色底形成视觉锚点，其余卡片保持浅色，避免四张卡视觉权重相同。
 */
export function KpiCards({ summary, refreshing }: KpiCardsProps) {
  const cards = [
    {
      index: "01",
      label: "总销售额",
      value: formatCompactCurrency(summary.revenue.value),
      previous: `上期 ${formatCompactCurrency(summary.revenue.previous)}`,
      metric: summary.revenue,
      series: summary.revenueSeries,
      stroke: "#7fc9a1",
      fill: "#7fc9a1",
      dark: true,
    },
    {
      index: "02",
      label: "有效订单",
      value: formatNumber(summary.orders.value),
      suffix: "单",
      previous: `上期 ${formatNumber(summary.orders.previous)} 单`,
      metric: summary.orders,
      series: summary.ordersSeries,
      stroke: "#1e6a49",
      fill: "#1e6a49",
      dark: false,
    },
    {
      index: "03",
      label: "销售件数",
      value: formatNumber(summary.units.value),
      suffix: "件",
      previous: `上期 ${formatNumber(summary.units.previous)} 件`,
      metric: summary.units,
      series: summary.unitsSeries,
      stroke: "#c9622f",
      fill: "#c9622f",
      dark: false,
    },
    {
      index: "04",
      label: "平均客单价",
      value: formatCurrencyPrecise(summary.avgOrderValue.value),
      previous: `上期 ${formatCurrencyPrecise(summary.avgOrderValue.previous)}`,
      metric: summary.avgOrderValue,
      series: summary.avgOrderValueSeries,
      stroke: "#3c6e9e",
      fill: "#3c6e9e",
      dark: false,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card, position) => (
        <article
          key={card.label}
          className={cn(
            "panel animate-rise relative flex flex-col overflow-hidden px-5 pt-4 pb-2 transition-opacity duration-300",
            card.dark && "border-ink bg-ink text-surface",
            refreshing && "opacity-85",
          )}
          style={{ animationDelay: `${position * 60}ms` }}
        >
          <div className="flex items-start justify-between">
            <span
              className={cn(
                "text-[11.5px] font-medium tracking-[0.06em]",
                card.dark ? "text-white/60" : "text-muted",
              )}
            >
              {card.label}
            </span>
            <span
              className={cn(
                "font-mono text-[10px] tracking-[0.18em]",
                card.dark ? "text-white/35" : "text-line-strong",
              )}
            >
              {card.index}
            </span>
          </div>

          <div className="mt-3 flex items-baseline gap-1.5">
            <span
              className={cn(
                "font-mono text-[27px] leading-none font-medium tracking-[-0.03em] tnum",
                card.dark ? "text-surface" : "text-ink",
              )}
            >
              {card.value}
            </span>
            {card.suffix && (
              <span className={cn("text-[12px]", card.dark ? "text-white/50" : "text-muted")}>{card.suffix}</span>
            )}
          </div>

          <div className="mt-2.5 flex items-center gap-2">
            <DeltaBadge metric={card.metric} tone={card.dark ? "dark" : "light"} />
            <span className={cn("truncate text-[11px] tnum", card.dark ? "text-white/45" : "text-muted")}>
              {card.previous}
            </span>
          </div>

          <div className={cn("mt-3 -mb-1", card.dark ? "opacity-90" : "opacity-80")}>
            <Sparkline values={card.series} stroke={card.stroke} fill={card.fill} />
          </div>
        </article>
      ))}
    </div>
  );
}
