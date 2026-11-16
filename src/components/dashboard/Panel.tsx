import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface PanelProps {
  /** 面板标题；为空时不渲染头部 */
  title?: ReactNode;
  subtitle?: ReactNode;
  /** 头部右侧的操作区，例如指标切换、刷新按钮 */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}

/**
 * 看板通用卡片容器。
 * 统一圆角、描边、内边距与头部排版，保证所有模块视觉一致。
 */
export function Panel({ title, subtitle, action, children, className, bodyClassName, id }: PanelProps) {
  return (
    <section id={id} className={cn("panel flex min-w-0 flex-col", className)}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 pt-4 pb-3">
          <div className="min-w-0">
            <h2 className="text-[13.5px] font-semibold tracking-[0.01em] text-ink">{title}</h2>
            {subtitle && <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  );
}
