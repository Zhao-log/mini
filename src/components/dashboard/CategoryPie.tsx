"use client";

import { useMemo } from "react";
import type { ChartOptions, TooltipItem } from "chart.js";
import { Doughnut } from "react-chartjs-2";
import "@/components/dashboard/chartSetup";
import { Panel } from "@/components/dashboard/Panel";
import { cn } from "@/lib/cn";
import { formatCompactCurrency, formatCurrency, formatRatio } from "@/lib/format";
import { CATEGORY_COLORS, CHART_THEME } from "@/lib/theme";
import type { Category, CategorySlice } from "@/lib/types";

interface CategoryPieProps {
  slices: CategorySlice[];
  /** 已选品类，用于高亮图例；为空表示全部 */
  selected: Category[];
  onToggleCategory: (category: Category) => void;
}

/**
 * 品类结构环形图。
 * 图例与扇区都可点击：点击后把该品类加入/移出筛选条件，
 * 从而联动表格、KPI 与趋势图。
 */
export function CategoryPie({ slices, selected, onToggleCategory }: CategoryPieProps) {
  const totalRevenue = useMemo(() => slices.reduce((sum, slice) => sum + slice.revenue, 0), [slices]);

  const options = useMemo<ChartOptions<"doughnut">>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      cutout: "72%",
      animation: { animateRotate: true, duration: 600 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: CHART_THEME.ink,
          titleColor: "#FFFDF8",
          bodyColor: "#FFFDF8",
          titleFont: { size: 11, weight: "normal" },
          bodyFont: { size: 12, weight: "bold" },
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
          callbacks: {
            label: (item: TooltipItem<"doughnut">) => {
              const slice = slices[item.dataIndex];
              if (!slice) return "";
              return `${formatCurrency(slice.revenue)} · 占比 ${formatRatio(slice.share)}`;
            },
          },
        },
      },
      onClick: (_event, elements) => {
        const index = elements[0]?.index;
        if (index === undefined) return;
        const slice = slices[index];
        if (slice) onToggleCategory(slice.category);
      },
    }),
    [slices, onToggleCategory],
  );

  const data = useMemo(
    () => ({
      labels: slices.map((slice) => slice.category),
      datasets: [
        {
          data: slices.map((slice) => slice.revenue),
          backgroundColor: slices.map((slice) => CATEGORY_COLORS[slice.category]),
          borderColor: CHART_THEME.surface,
          borderWidth: 2,
          hoverOffset: 6,
          hoverBorderColor: CHART_THEME.surface,
        },
      ],
    }),
    [slices],
  );

  if (slices.length === 0) {
    return (
      <Panel title="品类结构" subtitle="按营收占比统计" bodyClassName="px-5 pb-5">
        <div className="flex h-[190px] flex-col items-center justify-center gap-1 text-center">
          <span className="text-[13px] font-medium text-ink-soft">暂无品类数据</span>
          <span className="text-[11.5px] text-muted">当前筛选条件下没有有效订单</span>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="品类结构"
      subtitle="按营收占比排序"
      action={<span className="text-[11px] text-muted">{slices.length} 个品类</span>}
      bodyClassName="flex flex-col px-5 pb-5"
    >
      <div className="flex flex-1 flex-col items-center justify-center gap-4 sm:flex-row lg:flex-col lg:items-stretch xl:flex-row xl:items-center">
        <div className="relative mx-auto h-[158px] w-[158px] shrink-0 self-center">
          <Doughnut data={data} options={options} role="img" aria-label="各品类营收占比环形图" />
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-[10px] tracking-[0.14em] text-muted">总营收</span>
            <span className="mt-1 font-mono text-[16px] leading-none font-medium text-ink tnum">
              {formatCompactCurrency(totalRevenue)}
            </span>
          </div>
        </div>

        <ul className="w-full min-w-0 flex-1 space-y-0.5">
          {slices.map((slice) => {
            const active = selected.length === 0 || selected.includes(slice.category);
            return (
              <li key={slice.category}>
                <button
                  type="button"
                  onClick={() => onToggleCategory(slice.category)}
                  aria-pressed={selected.includes(slice.category)}
                  className={cn(
                    "flex w-full items-center gap-1.5 rounded-lg px-1.5 py-1.5 text-left transition-colors",
                    active ? "hover:bg-paper" : "opacity-55 hover:opacity-80",
                    selected.includes(slice.category) && "bg-forest-soft/70 hover:bg-forest-soft",
                  )}
                >
                  <span
                    className="size-2 shrink-0 rounded-[3px]"
                    style={{ backgroundColor: CATEGORY_COLORS[slice.category] }}
                  />
                  <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-soft">
                    {slice.category}
                  </span>
                  <span className="w-[36px] shrink-0 text-right font-mono text-[10.5px] text-muted tnum">
                    {formatRatio(slice.share)}
                  </span>
                  <span className="w-[58px] shrink-0 text-right font-mono text-[11px] text-ink tnum">
                    {formatCompactCurrency(slice.revenue)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      <p className="mt-3 border-t border-line pt-2.5 text-[10.5px] leading-relaxed text-muted">
        点击图形或图例可按品类下钻，再次点击取消该品类筛选。
      </p>
    </Panel>
  );
}
