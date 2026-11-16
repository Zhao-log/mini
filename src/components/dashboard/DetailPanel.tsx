"use client";

import { CategoryBadge, StatusBadge } from "@/components/dashboard/Badges";
import { Panel } from "@/components/dashboard/Panel";
import { CloseIcon, LayersIcon } from "@/components/dashboard/icons";
import { formatCurrency, formatCurrencyPrecise, formatLongDate, formatNumber, formatRatio } from "@/lib/format";
import { CATEGORY_COLORS, CATEGORY_SOFT_COLORS } from "@/lib/theme";
import type { SalesRecord } from "@/lib/types";

interface DetailPanelProps {
  record: SalesRecord | null;
  totalRevenue: number;
  totalRecords: number;
  onClose: () => void;
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line/80 bg-paper/40 px-3 py-2">
      <dt className="text-[10px] tracking-[0.06em] text-muted">{label}</dt>
      <dd className="mt-1 truncate font-mono text-[12px] text-ink tnum" title={value}>
        {value}
      </dd>
    </div>
  );
}

/**
 * 订单详情面板。
 *
 * 未选择订单时展示引导与区间摘要，避免右侧出现大面积空白；
 * 选中后展示金额构成、商品信息与占区间营收比例。
 */
export function DetailPanel({ record, totalRevenue, totalRecords, onClose }: DetailPanelProps) {
  if (!record) {
    return (
      <Panel
        title="订单详情"
        subtitle="选中表格中的一行以查看"
        className="self-start lg:sticky lg:top-[84px]"
        bodyClassName="px-5 pb-5"
      >
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <div className="relative flex size-20 items-center justify-center">
            <span className="absolute inset-0 rotate-6 rounded-2xl border border-line bg-paper-deep/70" />
            <span className="absolute inset-0 -rotate-3 rounded-2xl border border-line bg-surface" />
            <LayersIcon className="relative size-6 text-forest" />
          </div>
          <div>
            <p className="text-[13px] font-medium text-ink">尚未选择订单</p>
            <p className="mx-auto mt-1 max-w-[220px] text-[11.5px] leading-relaxed text-muted">
              点击左侧任意一行，查看商品、渠道、地区与金额明细。
            </p>
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-2 border-t border-line pt-4">
          <MetaItem label="区间营收" value={formatCurrency(totalRevenue)} />
          <MetaItem label="订单总数" value={`${formatNumber(totalRecords)} 笔`} />
        </dl>
      </Panel>
    );
  }

  const share = totalRevenue > 0 ? record.amount / totalRevenue : 0;
  const refunded = record.status === "已退款";

  return (
    <Panel
      title="订单详情"
      subtitle={<span className="font-mono text-[10.5px]">{record.id}</span>}
      action={
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭详情"
          className="-mt-1 flex size-6 items-center justify-center rounded-full text-muted transition-colors hover:bg-paper-deep hover:text-ink"
        >
          <CloseIcon className="size-3.5" />
        </button>
      }
      className="self-start lg:sticky lg:top-[84px]"
      bodyClassName="px-5 pb-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="text-[10.5px] tracking-[0.06em] text-muted">订单金额</span>
          <p className="mt-1 font-mono text-[26px] leading-none font-medium tracking-[-0.02em] text-ink tnum">
            {formatCurrencyPrecise(record.amount)}
          </p>
        </div>
        <StatusBadge status={record.status} className="mt-1" />
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between text-[10.5px] text-muted">
          <span>占区间营收</span>
          <span className="font-mono text-ink-soft tnum">{formatRatio(share, 2)}</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-paper-deep">
          <div
            className="h-full rounded-full bg-forest transition-[width] duration-500"
            style={{ width: `${Math.min(100, Math.max(1.5, share * 100))}%` }}
          />
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3 rounded-xl border border-line/80 bg-paper/40 p-3">
        <span
          className="flex size-10 shrink-0 items-center justify-center rounded-xl text-[13px] font-semibold"
          style={{
            backgroundColor: CATEGORY_SOFT_COLORS[record.category],
            color: CATEGORY_COLORS[record.category],
          }}
        >
          {record.category.slice(0, 1)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12.5px] font-medium text-ink" title={record.productName}>
            {record.productName}
          </p>
          <div className="mt-1 flex items-center gap-2">
            <CategoryBadge category={record.category} />
            <span className="font-mono text-[10px] text-muted">{record.productId}</span>
          </div>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2">
        <MetaItem label="交易日期" value={formatLongDate(record.date)} />
        <MetaItem label="销售渠道" value={record.channel} />
        <MetaItem label="销售地区" value={`${record.region}大区`} />
        <MetaItem label="数量 × 单价" value={`${record.quantity} × ${formatCurrency(record.unitPrice)}`} />
      </dl>

      {refunded && (
        <p className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-[11px] leading-relaxed text-danger">
          该订单已退款，金额不计入 KPI 与趋势统计。
        </p>
      )}

      <p className="mt-4 border-t border-line pt-2.5 text-[10.5px] leading-relaxed text-muted">
        数据每 15 秒自动同步，也可在筛选栏手动刷新。
      </p>
    </Panel>
  );
}
