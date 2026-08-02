import {
  ApiOutlined,
  CheckCircleFilled,
  CloudServerOutlined,
  DatabaseOutlined,
  RobotOutlined,
  WarningFilled,
} from "@ant-design/icons";
import type { DashboardSummary } from "../types";

export function InfrastructureHealth({
  summary,
}: {
  summary: DashboardSummary;
}) {
  const activeWorkers = summary.workers.filter((worker) => !worker.stale).length;
  const items = [
    {
      label: "Redis / 队列",
      value: summary.health.redis,
      detail: summary.queue.connected
        ? `延迟 ${summary.queue.latency_ms ?? 0}ms · 排队 ${summary.queue.queued}`
        : summary.queue.error || "连接失败",
      ok: summary.queue.connected,
      icon: <CloudServerOutlined />,
    },
    {
      label: "Worker",
      value: summary.health.workers,
      detail: `${activeWorkers} 个在线 · ${summary.workers.filter((item) => item.state === "busy").length} 个运行中`,
      ok: activeWorkers > 0,
      icon: <RobotOutlined />,
    },
    {
      label: "模型服务",
      value: summary.health.model,
      detail: `${summary.health.provider_mode.toUpperCase()} 模式`,
      ok: summary.health.model === "可用",
      icon: <ApiOutlined />,
    },
    {
      label: "存储服务",
      value: summary.health.database,
      detail: "关系型数据库已连接",
      ok: summary.health.database === "正常",
      icon: <DatabaseOutlined />,
    },
  ];
  return (
    <section className="health-strip" aria-label="基础设施状态">
      {items.map((item) => (
        <div className="health-strip__item" key={item.label}>
          <span className="health-strip__icon">{item.icon}</span>
          <div>
            <div className="health-strip__title">
              {item.label}
              <span className={item.ok ? "health-ok" : "health-warning"}>
                {item.ok ? <CheckCircleFilled /> : <WarningFilled />} {item.value}
              </span>
            </div>
            <small>{item.detail}</small>
          </div>
        </div>
      ))}
    </section>
  );
}

