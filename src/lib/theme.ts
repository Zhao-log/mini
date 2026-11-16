import type { Category } from "@/lib/types";

/**
 * 品类视觉映射：图表色板与标签配色共用一套，
 * 保证「饼图 → 表格 → 详情面板」中同一品类颜色一致。
 */
export const CATEGORY_COLORS: Record<Category, string> = {
  电子产品: "#1E6A49",
  运动用品: "#C9622F",
  家电: "#3C6E9E",
  家具: "#B08A3E",
  日用品: "#7C6A9C",
};

/** 品类标签的浅色底（与 CATEGORY_COLORS 一一对应） */
export const CATEGORY_SOFT_COLORS: Record<Category, string> = {
  电子产品: "#E5EFE8",
  运动用品: "#F8E9DE",
  家电: "#E4EDF5",
  家具: "#F5EEDD",
  日用品: "#EEEAF5",
};

/** 图表通用配色 */
export const CHART_THEME = {
  ink: "#15160F",
  muted: "#7B7A6D",
  grid: "#E7E3D7",
  axis: "#A6A394",
  forest: "#1E6A49",
  clay: "#C9622F",
  surface: "#FFFEFA",
} as const;
