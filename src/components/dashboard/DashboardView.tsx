"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CategoryPie } from "@/components/dashboard/CategoryPie";
import { DashboardSkeleton, EmptyState, ErrorState, InlineError } from "@/components/dashboard/StateViews";
import { DataTable } from "@/components/dashboard/DataTable";
import { DetailPanel } from "@/components/dashboard/DetailPanel";
import { FilterBar } from "@/components/dashboard/FilterBar";
import { KpiCards } from "@/components/dashboard/KpiCards";
import { TrendChart } from "@/components/dashboard/TrendChart";
import { ArrowUpRightIcon } from "@/components/dashboard/icons";
import { REFRESH_INTERVAL, useDashboardData } from "@/hooks/useDashboardData";
import { isMockMode } from "@/lib/api";
import { formatDateTime, formatLongDate, formatNumber, formatRelativeTime } from "@/lib/format";
import type { SalesRecord } from "@/lib/types";

/**
 * 销售分析看板主视图。
 *
 * 数据流：FilterBar → useDashboardData（请求/状态机）→ KPI / 图表 / 表格 / 详情。
 * 页面上只保留「选中订单」这一份交互态，其余状态全部收敛在 hook 中。
 */
export function DashboardView() {
  const controller = useDashboardData();
  const { data, status, error, filters, lastUpdated } = controller;

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const detailRef = useRef<HTMLDivElement>(null);

  // “最后更新 N 秒前”需要定时重算
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10_000);
    return () => window.clearInterval(timer);
  }, []);

  const selectedRecord = useMemo<SalesRecord | null>(
    () => data?.records.find((record) => record.id === selectedId) ?? null,
    [data, selectedId],
  );

  const filterSignature = `${filters.start}|${filters.end}|${filters.categories.join(",")}|${filters.query}`;
  const hasActiveFilters =
    filters.preset !== 30 || filters.categories.length > 0 || filters.query.trim().length > 0;
  const totalRevenue = data?.summary.revenue.value ?? 0;

  /** 移动端详情面板位于表格下方，选中后自动滚动过去，避免用户误以为没有响应 */
  const handleSelect = (record: SalesRecord) => {
    setSelectedId(record.id);
    if (window.matchMedia("(max-width: 1023px)").matches) {
      window.requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  };

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line/80 bg-paper/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1340px] items-center gap-3 px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2.5">
            <span className="flex size-7 items-center justify-center rounded-[9px] bg-ink font-mono text-[13px] font-semibold text-surface">
              M
            </span>
            <div className="leading-none">
              <p className="text-[13px] font-semibold tracking-[0.01em]">Meridian</p>
              <p className="mt-1 hidden text-[9.5px] tracking-[0.18em] text-muted sm:block">SALES ANALYTICS</p>
            </div>
          </div>

          <nav className="ml-6 hidden items-center gap-1 md:flex" aria-label="页面导航">
            {[
              { href: "#overview", label: "概览" },
              { href: "#trend", label: "趋势" },
              { href: "#records", label: "明细" },
            ].map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-full px-2.5 py-1 text-[12px] text-muted transition-colors hover:bg-paper-deep hover:text-ink"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[10.5px] text-muted sm:flex">
              <span className="live-dot size-1.5 rounded-full bg-forest text-forest" />
              每 {REFRESH_INTERVAL / 1000} 秒自动同步
            </span>
            <span
              className="rounded-full border border-line bg-surface px-2.5 py-1 font-mono text-[10px] tracking-[0.04em] text-ink-soft"
              title={isMockMode() ? "当前使用本地生成数据，不会请求后端" : "数据来自后端 analytics 接口"}
            >
              {isMockMode() ? "DEMO DATA" : "LIVE API"}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1340px] px-4 pt-1 pb-12 sm:px-6 lg:px-8">
        <section id="overview" className="flex flex-wrap items-end justify-between gap-4 pt-6 pb-5">
          <div>
            <div className="flex items-center gap-2 text-[10px] tracking-[0.18em] text-muted">
              <span className="h-px w-6 bg-line-strong" />
              SALES OVERVIEW
            </div>
            <h1 className="mt-2 text-[26px] leading-tight font-semibold tracking-[-0.02em] sm:text-[30px]">
              经营概览
            </h1>
            <p className="mt-1.5 text-[12.5px] text-muted">
              {formatLongDate(filters.start)} — {formatLongDate(filters.end)}
              {data && <span> · 共 {formatNumber(data.totalRecords)} 笔订单</span>}
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-[10px] tracking-[0.1em] text-muted">最后更新</p>
              <p className="mt-1 font-mono text-[11.5px] text-ink-soft tnum">
                {lastUpdated
                  ? formatRelativeTime(lastUpdated, now)
                  : status === "error"
                    ? "未获取数据"
                    : "同步中…"}
              </p>
            </div>
            <span className="h-8 w-px bg-line" />
            <a
              href="#records"
              className="flex items-center gap-1 rounded-full border border-line bg-surface px-3 py-1.5 text-[11.5px] font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
            >
              查看明细
              <ArrowUpRightIcon className="size-3.5" />
            </a>
          </div>
        </section>

        <FilterBar
          filters={filters}
          status={status}
          onPreset={controller.applyPreset}
          onCustomRange={controller.applyCustomRange}
          onToggleCategory={controller.toggleCategory}
          onClearCategories={() => controller.updateFilters({ categories: [] })}
          onQueryChange={controller.setQuery}
          onRefresh={controller.refresh}
          onReset={controller.resetFilters}
        />

        <div className="mt-3 space-y-3">
          {error && data && <InlineError message={error} onRetry={controller.retry} />}

          {status === "loading" && !data && <DashboardSkeleton />}

          {status === "error" && !data && <ErrorState message={error ?? "未知错误"} onRetry={controller.retry} />}

          {data && data.totalRecords === 0 && (
            <EmptyState onReset={controller.resetFilters} filtered={hasActiveFilters} />
          )}

          {data && data.totalRecords > 0 && (
            <>
              <KpiCards summary={data.summary} refreshing={status === "refreshing"} />

              <div id="trend" className="grid gap-3 lg:grid-cols-3">
                <div className="min-w-0 lg:col-span-2">
                  <TrendChart trend={data.trend} metric={filters.metric} onMetricChange={controller.setMetric} />
                </div>
                <CategoryPie
                  slices={data.categories}
                  selected={filters.categories}
                  onToggleCategory={controller.toggleCategory}
                />
              </div>

              <div id="records" className="grid gap-3 lg:grid-cols-3">
                <div className="min-w-0 lg:col-span-2">
                  <DataTable
                    records={data.records}
                    selectedId={selectedId}
                    onSelect={handleSelect}
                    filterSignature={filterSignature}
                  />
                </div>
                <div ref={detailRef} className="min-w-0 scroll-mt-20">
                  <DetailPanel
                    record={selectedRecord}
                    totalRevenue={totalRevenue}
                    totalRecords={data.totalRecords}
                    onClose={() => setSelectedId(null)}
                  />
                </div>
              </div>
            </>
          )}
        </div>

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4 text-[10.5px] text-muted">
          <span>Meridian 销售分析 · 退款订单不计入营收与订单量</span>
          <span className="font-mono tnum">{lastUpdated ? formatDateTime(lastUpdated) : ""}</span>
        </footer>
      </main>
    </div>
  );
}
