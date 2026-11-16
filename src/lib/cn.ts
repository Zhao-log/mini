/** 轻量 className 组合工具，避免为了一个函数引入 clsx 依赖 */
export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}
