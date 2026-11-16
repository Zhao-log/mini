"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DashboardApiError, fetchDashboard } from "@/lib/api";
import { addDays, toISODate } from "@/lib/format";
import {
  CATEGORIES,
  type Category,
  type DashboardData,
  type DashboardFilters,
  type LoadStatus,
  type MetricKey,
  type RangePreset,
} from "@/lib/types";

/** 自动刷新间隔（毫秒）。仅在标签页可见时触发，避免后台无意义请求。 */
export const REFRESH_INTERVAL = 15_000;

/** 最近 N 天（含今天）的日期区间 */
function rangeForPreset(days: 7 | 30 | 90): { start: string; end: string } {
  const end = new Date();
  return { start: toISODate(addDays(end, -(days - 1))), end: toISODate(end) };
}

export function createDefaultFilters(): DashboardFilters {
  return {
    preset: 30,
    ...rangeForPreset(30),
    categories: [],
    query: "",
    metric: "revenue",
  };
}

export interface DashboardController {
  /** 当前生效的筛选条件 */
  filters: DashboardFilters;
  /** 最近一次成功返回的数据；请求失败时保留上一份，避免页面闪空 */
  data: DashboardData | null;
  status: LoadStatus;
  error: string | null;
  lastUpdated: Date | null;
  isAutoRefreshEnabled: boolean;
  updateFilters: (patch: Partial<DashboardFilters>) => void;
  applyPreset: (preset: RangePreset) => void;
  applyCustomRange: (start: string, end: string) => void;
  toggleCategory: (category: Category) => void;
  setQuery: (query: string) => void;
  setMetric: (metric: MetricKey) => void;
  resetFilters: () => void;
  refresh: () => void;
  retry: () => void;
}

/**
 * 看板数据控制器：集中管理「筛选条件 → 请求 → 状态机 → 自动刷新」。
 *
 * 关键设计：
 * 1. 每次请求生成自增序号，只有最新请求可以写入状态，杜绝慢请求覆盖新结果；
 * 2. 新请求会 abort 上一个请求，切换筛选时不会堆积网络开销；
 * 3. 首次加载展示骨架屏，刷新时保留旧数据并在顶部显示进度，避免布局跳动。
 */
export function useDashboardData(): DashboardController {
  const [filters, setFilters] = useState<DashboardFilters>(createDefaultFilters);
  const [data, setData] = useState<DashboardData | null>(null);
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const filtersRef = useRef(filters);
  const requestSeq = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const hasDataRef = useRef(false);

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  const load = useCallback(async (next: DashboardFilters) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;

    setStatus(hasDataRef.current ? "refreshing" : "loading");

    try {
      const payload = await fetchDashboard(next, controller.signal);
      if (seq !== requestSeq.current) return;
      setData(payload);
      setLastUpdated(new Date(payload.updatedAt));
      hasDataRef.current = true;
      setError(null);
      setStatus("success");
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (seq !== requestSeq.current) return;
      setError(caught instanceof DashboardApiError ? caught.message : "数据加载失败，请稍后重试");
      setStatus("error");
    }
  }, []);

  // 筛选条件变化即重新请求；metric 只影响图表展示，故意不进入依赖
  const { start, end, categories, query } = filters;
  useEffect(() => {
    void load(filtersRef.current);
  }, [start, end, categories, query, load]);

  // 组件卸载时终止在途请求
  useEffect(() => () => abortRef.current?.abort(), []);

  // 自动刷新：仅在页面可见时执行
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load(filtersRef.current);
    }, REFRESH_INTERVAL);
    return () => window.clearInterval(timer);
  }, [load]);

  const updateFilters = useCallback((patch: Partial<DashboardFilters>) => {
    setFilters((previous) => ({ ...previous, ...patch }));
  }, []);

  const applyPreset = useCallback(
    (preset: RangePreset) => {
      if (preset === "custom") {
        updateFilters({ preset });
        return;
      }
      updateFilters({ preset, ...rangeForPreset(preset) });
    },
    [updateFilters],
  );

  const applyCustomRange = useCallback(
    (startDate: string, endDate: string) => {
      const [from, to] = startDate <= endDate ? [startDate, endDate] : [endDate, startDate];
      updateFilters({ preset: "custom", start: from, end: to });
    },
    [updateFilters],
  );

  const toggleCategory = useCallback(
    (category: Category) => {
      setFilters((previous) => {
        const selected = previous.categories.includes(category)
          ? previous.categories.filter((item) => item !== category)
          : [...previous.categories, category];
        return {
          ...previous,
          categories: CATEGORIES.filter((item) => selected.includes(item)),
        };
      });
    },
    [],
  );

  const setQuery = useCallback((value: string) => updateFilters({ query: value }), [updateFilters]);

  const setMetric = useCallback((metric: MetricKey) => updateFilters({ metric }), [updateFilters]);

  const resetFilters = useCallback(() => setFilters(createDefaultFilters()), []);

  const refresh = useCallback(() => void load(filtersRef.current), [load]);

  const retry = useCallback(() => {
    setError(null);
    setStatus(hasDataRef.current ? "refreshing" : "loading");
    void load(filtersRef.current);
  }, [load]);

  return {
    filters,
    data,
    status,
    error,
    lastUpdated,
    isAutoRefreshEnabled: true,
    updateFilters,
    applyPreset,
    applyCustomRange,
    toggleCategory,
    setQuery,
    setMetric,
    resetFilters,
    refresh,
    retry,
  };
}
