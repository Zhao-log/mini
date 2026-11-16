import { DashboardView } from "@/components/dashboard/DashboardView";

/** 首页：销售分析看板 */
export default function HomePage() {
  return (
    <>
      <div className="page-backdrop" aria-hidden="true" />
      <DashboardView />
    </>
  );
}
