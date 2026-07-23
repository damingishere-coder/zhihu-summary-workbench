import { Button, Timeline } from "antd";
import { useNavigate } from "react-router-dom";
import type { TaskLog } from "../types";
import { formatDateTime } from "../utils/format";

export function ActivityRail({ logs }: { logs: TaskLog[] }) {
  const navigate = useNavigate();
  return (
    <aside className="activity-rail" aria-label="操作日志">
      <div className="activity-rail__header">
        <strong>操作日志</strong>
        <Button type="link" size="small" onClick={() => navigate("/tasks")}>
          更多
        </Button>
      </div>
      {logs.length ? (
        <Timeline
          items={logs.slice(0, 9).map((log) => ({
            color: log.level === "error" ? "red" : log.level === "warning" ? "orange" : "blue",
            content: (
              <div className="activity-rail__item">
                <time>{formatDateTime(log.created_at)}</time>
                <p>{log.message}</p>
              </div>
            ),
          }))}
        />
      ) : (
        <p className="activity-rail__empty">任务开始后，这里会实时记录系统操作。</p>
      )}
    </aside>
  );
}
