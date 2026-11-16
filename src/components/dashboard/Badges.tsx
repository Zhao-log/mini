import { cn } from "@/lib/cn";
import { CATEGORY_COLORS, CATEGORY_SOFT_COLORS } from "@/lib/theme";
import type { Category, SalesStatus } from "@/lib/types";

/** 品类标签：色点与饼图颜色保持一致 */
export function CategoryBadge({ category, className }: { category: Category; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-[2px] text-[10.5px] font-medium whitespace-nowrap",
        className,
      )}
      style={{ backgroundColor: CATEGORY_SOFT_COLORS[category], color: CATEGORY_COLORS[category] }}
    >
      <span className="size-1.5 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[category] }} />
      {category}
    </span>
  );
}

const STATUS_STYLES: Record<SalesStatus, string> = {
  已完成: "bg-forest-soft text-forest",
  待发货: "bg-[#f5eedd] text-[#8a6a1f]",
  已退款: "bg-danger-soft text-danger",
};

export function StatusBadge({ status, className }: { status: SalesStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-[2px] text-[10.5px] font-medium whitespace-nowrap",
        STATUS_STYLES[status],
        className,
      )}
    >
      {status}
    </span>
  );
}
