import { buildEmptyDashboard, buildMockDashboard } from "@/lib/mock";
import type { DashboardData, DashboardFilters } from "@/lib/types";

/**
 * 数据访问层。
 *
 * - 生产/联调：请求 `NEXT_PUBLIC_API_BASE`（默认 http://localhost:8000/api/v1）
 * - 离线演示：`NEXT_PUBLIC_API_MOCK=1` 使用本地确定性数据
 * - 状态自测：`NEXT_PUBLIC_API_MOCK=empty | error` 分别模拟空数据与接口异常
 *
 * 接口约定见 components/dashboard/README.md，响应同时兼容
 * `{ data: DashboardData }`、`{ code, data }` 与裸对象三种包装。
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

const MOCK_MODE = (process.env.NEXT_PUBLIC_API_MOCK ?? "off").toLowerCase();
const REQUEST_TIMEOUT = 12_000;

export class DashboardApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "DashboardApiError";
    this.status = status;
  }
}

/** 是否处于本地演示模式（用于页面角标展示） */
export function isMockMode(): boolean {
  return MOCK_MODE === "1" || MOCK_MODE === "true" || MOCK_MODE === "empty" || MOCK_MODE === "error";
}

function buildQuery(filters: DashboardFilters): string {
  const params = new URLSearchParams();
  params.set("start_date", filters.start);
  params.set("end_date", filters.end);
  filters.categories.forEach((category) => params.append("category", category));
  if (filters.query.trim()) params.set("q", filters.query.trim());
  return params.toString();
}

function abortError(): Error {
  return new DOMException("请求已取消", "AbortError");
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const handleAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", handleAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", handleAbort, { once: true });
  });
}

/** 兼容不同的后端响应包装 */
function unwrapPayload(payload: unknown): DashboardData {
  if (!payload || typeof payload !== "object") {
    throw new DashboardApiError("接口返回了无法解析的内容");
  }
  const wrapper = payload as Record<string, unknown>;
  const candidate = (wrapper.data ?? wrapper.result ?? payload) as Record<string, unknown> | null;

  if (
    !candidate ||
    typeof candidate !== "object" ||
    !("summary" in candidate) ||
    !("trend" in candidate) ||
    !("records" in candidate)
  ) {
    throw new DashboardApiError("接口响应格式与看板约定不一致，缺少 summary / trend / records 字段");
  }
  return candidate as unknown as DashboardData;
}

/**
 * 解析当前 mock 模式。
 * 开发环境额外支持 `?mock=empty|error|1` 覆盖，方便在浏览器里直接验收
 * 空状态与异常状态（生产构建中该分支会被整体剔除）。
 */
function resolveMockMode(): string {
  if (process.env.NODE_ENV !== "production" && typeof window !== "undefined") {
    const override = new URLSearchParams(window.location.search).get("mock");
    if (override === "empty" || override === "error" || override === "1") return override;
  }
  return MOCK_MODE;
}

/** 拉取看板数据；调用方负责传入 AbortSignal 以取消过期请求 */
export async function fetchDashboard(
  filters: DashboardFilters,
  signal?: AbortSignal,
): Promise<DashboardData> {
  const mode = resolveMockMode();
  if (mode === "error") {
    await sleep(600, signal);
    throw new DashboardApiError("演示模式：模拟服务端 503，请稍后重试", 503);
  }
  if (mode === "empty") {
    await sleep(400, signal);
    return buildEmptyDashboard(filters);
  }
  if (mode === "1" || mode === "true") {
    await sleep(420, signal);
    return buildMockDashboard(filters);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
  const forwardAbort = () => controller.abort();
  signal?.addEventListener("abort", forwardAbort, { once: true });

  try {
    const response = await fetch(`${API_BASE}/analytics/dashboard?${buildQuery(filters)}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
      cache: "no-store",
    });

    if (!response.ok) {
      throw new DashboardApiError(
        response.status === 404
          ? "数据接口不存在（404），请核对 api.md 中的接口路径"
          : `数据服务返回异常状态 ${response.status}`,
        response.status,
      );
    }

    return unwrapPayload(await response.json());
  } catch (error) {
    if (error instanceof DashboardApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      if (signal?.aborted) throw error;
      throw new DashboardApiError("请求超时，数据服务在 12 秒内没有响应");
    }
    throw new DashboardApiError(
      `无法连接到数据服务（${API_BASE}）。请确认后端已启动，或设置 NEXT_PUBLIC_API_MOCK=1 使用本地演示数据。`,
    );
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", forwardAbort);
  }
}
