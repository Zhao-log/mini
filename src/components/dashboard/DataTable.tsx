"use client";

import { useEffect, useMemo, useState } from "react";
import { CategoryBadge, StatusBadge } from "@/components/dashboard/Badges";
import { Panel } from "@/components/dashboard/Panel";
import { ArrowLeftIcon, ArrowRightIcon } from "@/components/dashboard/icons";
import { cn } from "@/lib/cn";
import { formatAxisDate, formatCurrency, formatLongDate, formatNumber } from "@/lib/format";
import type { SalesRecord } from "@/lib/types";

type SortKey = "date" | "amount";
type SortState = { key: SortKey; direction: "asc" | "desc" };

interface DataTableProps {
  records: SalesRecord[];
  selectedId: string | null;
  onSelect: (record: SalesRecord) => void;
  /** 筛选签名变化时重置页码，避免停留在越界页 */
  filterSignature: string;
}

const PAGE_SIZE = 8;

function SortArrow({ active, direction }: { active: boolean; direction: "asc" | "desc" }) {
  return (
    <svg
      viewBox="0 0 10 12"
      className={cn("size-2.5 transition-transform", active ? "text-ink" : "text-line-strong", direction === "asc" && "rotate-180")}
      aria-hidden="true"
    >
      <path d="M5 10 1 5h8L5 10Z" fill="currentColor" />
    </svg>
  );
}

/**
 * 订单明细表格。
 * 采用前端分页（每页 8 条）与日期/金额排序，数据量级在千条以内性能足够；
 * 若后端提供分页接口，可把 page/pageSize 提升为受控 props。
 */
export function DataTable({ records, selectedId, onSelect, filterSignature }: DataTableProps) {
  const [sort, setSort] = useState<SortState>({ key: "date", direction: "desc" });
  const [page, setPage] = useState(0);

  useEffect(() => {
    setPage(0);
  }, [filterSignature]);

  const sorted = useMemo(() => {
    const list = [...records];
    list.sort((a, b) => {
      const factor = sort.direction === "asc" ? 1 : -1;
      if (sort.key === "amount") return (a.amount - b.amount) * factor || a.id.localeCompare(b.id);
      return (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id.localeCompare(b.id)) * factor;
    });
    return list;
  }, [records, sort]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = sorted.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  const toggleSort = (key: SortKey) => {
    setSort((previous) =>
      previous.key === key
        ? { key, direction: previous.direction === "desc" ? "asc" : "desc" }
        : { key, direction: "desc" },
    );
    setPage(0);
  };

  return (
    <Panel
      title="订单明细"
      subtitle="点击任意一行查看订单详情"
      action={
        <span className="font-mono text-[11px] text-muted tnum">
          {formatNumber(records.length)} 条
        </span>
      }
      bodyClassName="flex flex-col"
      className="min-h-[420px]"
    >
      {records.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1.5 px-5 py-14 text-center">
          <span className="text-[13px] font-medium text-ink-soft">没有符合条件的订单</span>
          <span className="text-[11.5px] text-muted">调整时间范围、品类或搜索关键词后再试</span>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <caption className="sr-only">销售订单明细列表</caption>
              <thead>
                <tr className="border-y border-line bg-paper/60">
                  <th scope="col" className="hidden px-4 py-2 text-[10.5px] font-medium tracking-[0.06em] text-muted sm:table-cell">
                    订单号
                  </th>
                  <th scope="col" className="px-4 py-2">
                    <button
                      type="button"
                      onClick={() => toggleSort("date")}
                      className="flex items-center gap-1 text-[10.5px] font-medium tracking-[0.06em] text-muted hover:text-ink"
                      aria-label="按日期排序"
                    >
                      日期
                      <SortArrow active={sort.key === "date"} direction={sort.direction} />
                    </button>
                  </th>
                  <th scope="col" className="px-3 py-2 text-[10.5px] font-medium tracking-[0.06em] text-muted">
                    商品
                  </th>
                  <th scope="col" className="hidden px-3 py-2 text-[10.5px] font-medium tracking-[0.06em] text-muted lg:table-cell">
                    渠道
                  </th>
                  <th scope="col" className="hidden px-3 py-2 text-right text-[10.5px] font-medium tracking-[0.06em] text-muted md:table-cell">
                    数量
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => toggleSort("amount")}
                      className="ml-auto flex items-center gap-1 text-[10.5px] font-medium tracking-[0.06em] text-muted hover:text-ink"
                      aria-label="按金额排序"
                    >
                      金额
                      <SortArrow active={sort.key === "amount"} direction={sort.direction} />
                    </button>
                  </th>
                  <th scope="col" className="px-4 py-2 text-[10.5px] font-medium tracking-[0.06em] text-muted">
                    状态
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((record) => {
                  const selected = record.id === selectedId;
                  return (
                    <tr
                      key={record.id}
                      tabIndex={0}
                      aria-selected={selected}
                      onClick={() => onSelect(record)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onSelect(record);
                        }
                      }}
                      className={cn(
                        "cursor-pointer border-b border-line/70 transition-colors last:border-0",
                        selected ? "bg-forest-soft/60" : "hover:bg-paper/70",
                      )}
                    >
                      <td className="hidden px-4 py-2.5 sm:table-cell">
                        <span className="font-mono text-[10.5px] whitespace-nowrap text-muted">
                          {record.id}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="font-mono text-[11.5px] whitespace-nowrap text-ink-soft tnum" title={formatLongDate(record.date)}>
                          {formatAxisDate(record.date)}
                        </span>
                      </td>
                      <td className="max-w-[210px] px-3 py-2.5">
                        <div className="truncate text-[12px] font-medium text-ink" title={record.productName}>
                          {record.productName}
                        </div>
                        <div className="mt-1">
                          <CategoryBadge category={record.category} />
                        </div>
                      </td>
                      <td className="hidden px-3 py-2.5 text-[11.5px] whitespace-nowrap text-muted lg:table-cell">
                        {record.channel}
                      </td>
                      <td className="hidden px-3 py-2.5 text-right font-mono text-[11.5px] text-ink-soft tnum md:table-cell">
                        {record.quantity}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-[12px] whitespace-nowrap text-ink tnum">
                        {formatCurrency(record.amount)}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={record.status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-2.5">
            <span className="font-mono text-[11px] text-muted tnum">
              第 {safePage * PAGE_SIZE + 1}–{Math.min(sorted.length, (safePage + 1) * PAGE_SIZE)} 条 · 共{" "}
              {sorted.length} 条
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setPage((value) => Math.max(0, value - 1))}
                disabled={safePage === 0}
                aria-label="上一页"
                className="flex size-7 items-center justify-center rounded-full border border-line text-muted transition-colors hover:border-line-strong hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ArrowLeftIcon className="size-3.5" />
              </button>
              <span className="min-w-[52px] text-center font-mono text-[11px] text-ink-soft tnum">
                {safePage + 1} / {pageCount}
              </span>
              <button
                type="button"
                onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
                disabled={safePage >= pageCount - 1}
                aria-label="下一页"
                className="flex size-7 items-center justify-center rounded-full border border-line text-muted transition-colors hover:border-line-strong hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ArrowRightIcon className="size-3.5" />
              </button>
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}
