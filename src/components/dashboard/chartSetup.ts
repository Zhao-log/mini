"use client";

import {
  ArcElement,
  CategoryScale,
  Chart as ChartJS,
  DoughnutController,
  Filler,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";

/**
 * Chart.js 按需注册。
 * 必须放在客户端模块中执行；只注册看板实际使用的控制器与元素，
 * 避免把整包 Chart.js（约 200KB）打进首屏。
 */
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  LineController,
  Filler,
  Tooltip,
  Legend,
  ArcElement,
  DoughnutController,
);

ChartJS.defaults.font.family = '"Segoe UI", ui-sans-serif, system-ui, -apple-system, sans-serif';
ChartJS.defaults.font.size = 11;
ChartJS.defaults.color = "#7b7a6d";

export { ChartJS };
