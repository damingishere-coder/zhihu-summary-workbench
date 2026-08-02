import type { DashboardSummary } from "../types";

export function MetricStrip({
  metrics,
}: {
  metrics: DashboardSummary["metrics"];
}) {
  const items = [
    { label: "今日计划", value: metrics.today_plan, tone: "neutral" },
    { label: "处理中", value: metrics.processing, tone: "info" },
    { label: "待审核", value: metrics.waiting_review, tone: "warning" },
    { label: "失败任务", value: metrics.failed, tone: "error" },
  ];
  return (
    <section className="metric-strip" aria-label="今日任务指标">
      {items.map((item) => (
        <div className={`metric-strip__item metric-strip__item--${item.tone}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <small>{item.label === "今日计划" ? "每日额度" : "实时统计"}</small>
        </div>
      ))}
    </section>
  );
}

