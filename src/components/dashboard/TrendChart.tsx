"use client";

import { useMemo } from "react";
import type { ChartOptions, ScriptableContext, TooltipItem } from "chart.js";
import { Line } from "react-chartjs-2";
import "@/components/dashboard/chartSetup";
import { Panel } from "@/components/dashboard/Panel";
import { cn } from "@/lib/cn";
import { formatCompactCurrency, formatCurrency, formatNumber } from "@/lib/format";
import { CHART_THEME } from "@/lib/theme";
import type { MetricKey, TrendPoint } from "@/lib/types";

interface TrendChartProps {
  trend: TrendPoint[];
  metric: MetricKey;
  onMetricChange: (metric: MetricKey) => void;
}

const METRIC_OPTIONS: Array<{ value: MetricKey; label: string }> = [
  { value: "revenue", label: "销售额" },
  { value: "orders", label: "订单量" },
];

/**
 * 销售趋势折线图。
 * 数据点由接口按「近 30 天按日 / 更长区间按周」聚合后返回，
 * 组件只负责展示与指标切换，不做二次聚合。
 */
export function TrendChart({ trend, metric, onMetricChange }: TrendChartProps) {
  const total = useMemo(
    () => trend.reduce((sum, point) => sum + (metric === "revenue" ? point.revenue : point.orders), 0),
    [trend, metric],
  );

  const options = useMemo<ChartOptions<"line">>(() => {
    const accent = metric === "revenue" ? CHART_THEME.forest : CHART_THEME.clay;
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      animation: { duration: 500 },
      layout: { padding: { top: 4, right: 2, left: 0, bottom: 0 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: CHART_THEME.ink,
          titleColor: "#FFFDF8",
          bodyColor: "#FFFDF8",
          titleFont: { size: 11, weight: "normal" },
          bodyFont: { size: 12.5, weight: "bold" },
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
          callbacks: {
            title: (items: TooltipItem<"line">[]) => items[0]?.label ?? "",
            label: (item: TooltipItem<"line">) => {
              const value = item.parsed.y ?? 0;
              return metric === "revenue"
                ? `销售额  ${formatCurrency(value)}`
                : `订单量  ${formatNumber(value)} 单`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: {
            color: CHART_THEME.axis,
            font: { size: 10.5 },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8,
            padding: 6,
          },
        },
        y: {
          beginAtZero: true,
          border: { display: false },
          grid: { color: CHART_THEME.grid, drawTicks: false },
          ticks: {
            color: CHART_THEME.axis,
            font: { size: 10.5 },
            padding: 8,
            maxTicksLimit: 5,
            callback: (value) =>
              metric === "revenue"
                ? formatCompactCurrency(Number(value))
                : formatNumber(Number(value)),
          },
        },
      },
      elements: {
        line: { borderColor: accent },
      },
    };
  }, [metric]);

  const data = useMemo(
    () => ({
      labels: trend.map((point) => point.label),
      datasets: [
        {
          label: metric === "revenue" ? "销售额" : "订单量",
          data: trend.map((point) => (metric === "revenue" ? point.revenue : point.orders)),
          borderColor: metric === "revenue" ? CHART_THEME.forest : CHART_THEME.clay,
          borderWidth: 2,
          tension: 0.35,
          fill: true,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBorderWidth: 2,
          pointHoverBackgroundColor: CHART_THEME.surface,
          pointHoverBorderColor: metric === "revenue" ? CHART_THEME.forest : CHART_THEME.clay,
          backgroundColor: (context: ScriptableContext<"line">) => {
            const { ctx, chartArea } = context.chart;
            if (!chartArea) return "rgba(30,106,73,0.06)";
            const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            if (metric === "revenue") {
              gradient.addColorStop(0, "rgba(30,106,73,0.20)");
              gradient.addColorStop(1, "rgba(30,106,73,0)");
            } else {
              gradient.addColorStop(0, "rgba(201,98,47,0.18)");
              gradient.addColorStop(1, "rgba(201,98,47,0)");
            }
            return gradient;
          },
        },
      ],
    }),
    [trend, metric],
  );

  return (
    <Panel
      title="销售趋势"
      subtitle={
        trend.length > 0
          ? `区间合计 ${metric === "revenue" ? formatCurrency(total) : `${formatNumber(total)} 单`} · ${trend.length} 个数据点`
          : "选定区间内暂无可用数据"
      }
      action={
        <div className="flex rounded-full border border-line bg-paper-deep/70 p-[3px]">
          {METRIC_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onMetricChange(option.value)}
              aria-pressed={metric === option.value}
              className={cn(
                "rounded-full px-2.5 py-1 text-[11.5px] transition-colors",
                metric === option.value
                  ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgba(23,24,15,0.08)]"
                  : "text-muted hover:text-ink",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      }
      bodyClassName="px-3 pb-3"
    >
      <div className="relative h-[260px] sm:h-[300px]">
        {trend.length > 1 ? (
          <Line data={data} options={options} aria-label="销售趋势折线图" role="img" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
            <span className="text-[13px] font-medium text-ink-soft">暂无趋势数据</span>
            <span className="text-[11.5px] text-muted">尝试放宽时间范围或清除品类筛选</span>
          </div>
        )}
      </div>
    </Panel>
  );
}
