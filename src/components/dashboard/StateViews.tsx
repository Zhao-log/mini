"use client";

import { AlertIcon, InboxIcon, RefreshIcon } from "@/components/dashboard/icons";

/** 首屏骨架屏：结构与真实内容一致，避免数据到达时布局跳动 */
export function DashboardSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="数据加载中">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="panel px-5 pt-4 pb-5">
            <div className="skeleton h-3 w-16" />
            <div className="skeleton mt-4 h-7 w-32" />
            <div className="skeleton mt-3 h-3 w-24" />
            <div className="skeleton mt-5 h-8 w-full" />
          </div>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="panel p-5 lg:col-span-2">
          <div className="skeleton h-3.5 w-20" />
          <div className="skeleton mt-2 h-3 w-40" />
          <div className="skeleton mt-5 h-[260px] w-full" />
        </div>
        <div className="panel p-5">
          <div className="skeleton h-3.5 w-20" />
          <div className="skeleton mt-2 h-3 w-28" />
          <div className="mt-5 flex items-center gap-4">
            <div className="skeleton size-[150px] shrink-0 rounded-full" />
            <div className="flex-1 space-y-2.5">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="skeleton h-3 w-full" />
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="panel p-5 lg:col-span-2">
          <div className="skeleton h-3.5 w-20" />
          <div className="mt-4 space-y-3">
            {Array.from({ length: 7 }).map((_, index) => (
              <div key={index} className="skeleton h-9 w-full" />
            ))}
          </div>
        </div>
        <div className="panel p-5">
          <div className="skeleton h-3.5 w-20" />
          <div className="skeleton mt-4 h-24 w-full" />
          <div className="skeleton mt-3 h-16 w-full" />
        </div>
      </div>
    </div>
  );
}

interface EmptyStateProps {
  onReset: () => void;
  /** 是否因为筛选条件导致无数据 */
  filtered?: boolean;
}

export function EmptyState({ onReset, filtered = true }: EmptyStateProps) {
  return (
    <div className="panel flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-forest-soft text-forest">
        <InboxIcon className="size-6" />
      </div>
      <h3 className="text-[15px] font-semibold text-ink">当前条件下没有销售记录</h3>
      <p className="max-w-[360px] text-[12px] leading-relaxed text-muted">
        {filtered
          ? "试着扩大时间范围、减少品类筛选，或清空搜索关键词后再查看。"
          : "所选区间内还没有产生订单，可以切换到最近 7 天或等待数据同步。"}
      </p>
      <button
        type="button"
        onClick={onReset}
        className="mt-1 rounded-full border border-ink bg-ink px-4 py-1.5 text-[12px] font-medium text-surface transition-colors hover:bg-ink-soft"
      >
        重置全部筛选
      </button>
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="panel flex flex-col items-center justify-center gap-3 border-danger/25 px-6 py-16 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-danger-soft text-danger">
        <AlertIcon className="size-6" />
      </div>
      <h3 className="text-[15px] font-semibold text-ink">数据加载失败</h3>
      <p className="max-w-[420px] text-[12px] leading-relaxed text-muted">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-1 flex items-center gap-1.5 rounded-full border border-ink bg-ink px-4 py-1.5 text-[12px] font-medium text-surface transition-colors hover:bg-ink-soft"
      >
        <RefreshIcon className="size-3.5" />
        重新加载
      </button>
      <p className="mt-1 font-mono text-[10.5px] text-muted/80">
        离线演示：NEXT_PUBLIC_API_MOCK=1 npm run dev
      </p>
    </div>
  );
}

/** 已有数据但刷新失败时的顶部提示，保留旧数据不闪空 */
export function InlineError({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-danger/25 bg-danger-soft/70 px-3.5 py-2"
    >
      <AlertIcon className="size-3.5 shrink-0 text-danger" />
      <span className="text-[11.5px] leading-relaxed text-danger">
        刷新失败，当前展示为上一次的数据。{message}
      </span>
      <button
        type="button"
        onClick={onRetry}
        className="ml-auto rounded-full border border-danger/30 px-2.5 py-0.5 text-[11px] font-medium text-danger transition-colors hover:bg-danger/10"
      >
        重试
      </button>
    </div>
  );
}
