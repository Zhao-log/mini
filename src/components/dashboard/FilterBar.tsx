"use client";

import { useEffect, useState } from "react";
import { CalendarIcon, CloseIcon, RefreshIcon, SearchIcon } from "@/components/dashboard/icons";
import { cn } from "@/lib/cn";
import { formatLongDate, toISODate } from "@/lib/format";
import { CATEGORY_COLORS } from "@/lib/theme";
import {
  CATEGORIES,
  type Category,
  type DashboardFilters,
  type LoadStatus,
  type RangePreset,
} from "@/lib/types";

const PRESETS: Array<{ value: Exclude<RangePreset, "custom">; label: string; hint: string }> = [
  { value: 7, label: "近 7 天", hint: "最近一周" },
  { value: 30, label: "近 30 天", hint: "最近一个月" },
  { value: 90, label: "近 90 天", hint: "最近一个季度" },
];

interface FilterBarProps {
  filters: DashboardFilters;
  status: LoadStatus;
  onPreset: (preset: RangePreset) => void;
  onCustomRange: (start: string, end: string) => void;
  onToggleCategory: (category: Category) => void;
  onClearCategories: () => void;
  onQueryChange: (query: string) => void;
  onRefresh: () => void;
  onReset: () => void;
}

/**
 * 交互式筛选区。
 *
 * - 时间：预设区间 + 自定义日期（修改任意日期会自动切换为「自定义」）
 * - 品类：多选 chips，空数组即全部
 * - 搜索：300ms 防抖，避免每次键入都触发请求
 * - 刷新：手动拉取最新数据，加载中显示旋转图标
 */
export function FilterBar({
  filters,
  status,
  onPreset,
  onCustomRange,
  onToggleCategory,
  onClearCategories,
  onQueryChange,
  onRefresh,
  onReset,
}: FilterBarProps) {
  const [keyword, setKeyword] = useState(filters.query);
  const [keywordFocus, setKeywordFocus] = useState(false);
  const busy = status === "loading" || status === "refreshing";
  const today = toISODate(new Date());

  // 外部重置筛选时同步输入框
  useEffect(() => {
    setKeyword(filters.query);
  }, [filters.query]);

  // 输入防抖：停止输入 300ms 后才真正查询
  useEffect(() => {
    if (keyword === filters.query) return;
    const timer = window.setTimeout(() => onQueryChange(keyword.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [keyword, filters.query, onQueryChange]);

  const dirty =
    filters.preset !== 30 || filters.categories.length > 0 || filters.query.trim().length > 0;

  return (
    <section className="panel px-3 py-3 sm:px-4" aria-label="数据筛选">
      <div className="flex flex-wrap items-center gap-2">
        {/* 时间预设 */}
        <div className="flex rounded-full border border-line bg-paper-deep/70 p-[3px]">
          {PRESETS.map((preset) => (
            <button
              key={preset.value}
              type="button"
              title={preset.hint}
              onClick={() => onPreset(preset.value)}
              aria-pressed={filters.preset === preset.value}
              className={cn(
                "rounded-full px-3 py-1.5 text-[12px] transition-colors",
                filters.preset === preset.value
                  ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgba(23,24,15,0.08)]"
                  : "text-muted hover:text-ink",
              )}
            >
              {preset.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => onPreset("custom")}
            aria-pressed={filters.preset === "custom"}
            className={cn(
              "rounded-full px-3 py-1.5 text-[12px] transition-colors",
              filters.preset === "custom"
                ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgba(23,24,15,0.08)]"
                : "text-muted hover:text-ink",
            )}
          >
            自定义
          </button>
        </div>

        {/* 自定义日期 */}
        <div className="flex items-center gap-1.5">
          <label className="flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 transition-colors focus-within:border-forest">
            <CalendarIcon className="size-3.5 shrink-0 text-muted" />
            <input
              type="date"
              aria-label="开始日期"
              value={filters.start}
              max={filters.end > today ? today : filters.end}
              onChange={(event) => onCustomRange(event.target.value, filters.end)}
              className="w-[112px] bg-transparent font-mono text-[11.5px] text-ink outline-none tnum"
            />
          </label>
          <span className="text-muted">–</span>
          <label className="flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 transition-colors focus-within:border-forest">
            <CalendarIcon className="size-3.5 shrink-0 text-muted" />
            <input
              type="date"
              aria-label="结束日期"
              value={filters.end}
              min={filters.start}
              max={today}
              onChange={(event) => onCustomRange(filters.start, event.target.value)}
              className="w-[112px] bg-transparent font-mono text-[11.5px] text-ink outline-none tnum"
            />
          </label>
        </div>

        <div className="ml-auto flex w-full items-center gap-2 sm:w-auto">
          {/* 搜索 */}
          <div className="relative min-w-0 flex-1 sm:flex-none">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-muted" />
            <input
              type="search"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onFocus={() => setKeywordFocus(true)}
              onBlur={() => setKeywordFocus(false)}
              placeholder="搜索商品 / 订单 / 地区"
              aria-label="搜索订单"
              className={cn(
                "h-9 w-full rounded-full border bg-surface pr-8 pl-8 text-[12px] text-ink outline-none transition-colors placeholder:text-muted/80 sm:w-[220px]",
                keywordFocus ? "border-forest" : "border-line",
              )}
            />
            {keyword && (
              <button
                type="button"
                onClick={() => {
                  setKeyword("");
                  onQueryChange("");
                }}
                aria-label="清除搜索"
                className="absolute top-1/2 right-2.5 -translate-y-1/2 rounded-full p-0.5 text-muted hover:bg-paper-deep hover:text-ink"
              >
                <CloseIcon className="size-3" />
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={onRefresh}
            disabled={busy}
            className="flex h-9 items-center gap-1.5 rounded-full border border-ink bg-ink px-3.5 text-[12px] font-medium text-surface transition-colors hover:bg-ink-soft disabled:cursor-wait disabled:opacity-80"
          >
            <RefreshIcon className={cn("size-3.5", busy && "spin")} />
            <span className="hidden sm:inline">{busy ? "同步中" : "刷新"}</span>
          </button>
        </div>
      </div>

      {/* 品类筛选 */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
        <span className="mr-1 text-[11px] tracking-[0.06em] text-muted">品类</span>
        <button
          type="button"
          onClick={onClearCategories}
          aria-pressed={filters.categories.length === 0}
          className={cn(
            "rounded-full border px-3 py-1.5 text-[11.5px] transition-colors",
            filters.categories.length === 0
              ? "border-ink bg-ink text-surface"
              : "border-line bg-surface text-ink-soft hover:border-line-strong",
          )}
        >
          全部
        </button>
        {CATEGORIES.map((category) => {
          const selected = filters.categories.includes(category);
          return (
            <button
              key={category}
              type="button"
              onClick={() => onToggleCategory(category)}
              aria-pressed={selected}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11.5px] transition-colors",
                selected
                  ? "border-ink bg-ink text-surface"
                  : "border-line bg-surface text-ink-soft hover:border-line-strong",
              )}
            >
              <span
                className="size-1.5 rounded-full"
                style={{ backgroundColor: selected ? "#fffdf8" : CATEGORY_COLORS[category] }}
              />
              {category}
            </button>
          );
        })}

        {dirty && (
          <button
            type="button"
            onClick={onReset}
            className="ml-1 flex items-center gap-1 rounded-full px-2 py-1.5 text-[11.5px] text-muted transition-colors hover:text-ink"
          >
            <CloseIcon className="size-3" />
            重置筛选
          </button>
        )}

        <span className="ml-auto hidden items-center gap-1 text-[11px] text-muted md:flex">
          当前区间
          <span className="font-mono text-ink-soft tnum">
            {formatLongDate(filters.start)} — {formatLongDate(filters.end)}
          </span>
        </span>
      </div>
    </section>
  );
}
