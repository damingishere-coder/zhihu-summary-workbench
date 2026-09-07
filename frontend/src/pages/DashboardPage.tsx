import { ArrowRightOutlined, CheckCircleOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Collapse } from "antd";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { allDrafts, allTasks } from "../api/collections";
import { InfrastructureHealth } from "../components/InfrastructureHealth";
import { ProductionPlanPanel } from "../components/ProductionPlanPanel";
import { PageHeader } from "../components/PageHeader";
import { SectionNav } from "../components/SectionNav";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import {
  attentionStatuses,
  runningStatuses,
  taskAction,
} from "../utils/taskActions";
import { formatDateTime } from "../utils/format";
import type { Task } from "../types";

function TaskRows({ tasks }: { tasks: Task[] }) {
  return (
    <div className="action-list">
      {tasks.map((task) => {
        const action = taskAction(task);
        return (
          <div className="action-row" key={task.id}>
            <div>
              <Link className="action-title" to={action.href}>
                {task.question_title}
              </Link>
              <p>
                {task.error_message || (
                  <>
                    <StatusTag status={task.stage} /> {task.progress}%
                  </>
                )}
              </p>
            </div>
            <Link className="quiet-link" to={action.href}>
              {action.label} <ArrowRightOutlined />
            </Link>
          </div>
        );
      })}
    </div>
  );
}

export function DashboardPage() {
  const summary = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    refetchInterval: 15000,
  });
  const tasks = useQuery({
    queryKey: ["tasks", "all"],
    queryFn: () => allTasks(),
    refetchInterval: 15000,
  });
  const drafts = useQuery({ queryKey: ["drafts", "all"], queryFn: allDrafts });
  const attention =
    tasks.data?.items.filter((task) =>
      attentionStatuses.includes(task.status),
    ) ?? [];
  const running =
    tasks.data?.items.filter((task) => runningStatuses.includes(task.status)) ??
    [];
  const waiting =
    drafts.data?.items.filter((draft) => draft.status !== "review_approved") ??
    [];
  const healthy =
    summary.data &&
    summary.data.queue.connected &&
    summary.data.workers.some((worker) => !worker.stale) &&
    summary.data.health.model === "可用" &&
    summary.data.health.database === "正常";
  return (
    <div className="page page--dashboard">
      <PageHeader
        eyebrow={new Date().toLocaleDateString("zh-CN", {
          month: "long",
          day: "numeric",
          weekday: "long",
        })}
        title="今天"
        actions={
          <Link className="quiet-link" to="/questions">
            添加选题 <ArrowRightOutlined />
          </Link>
        }
      />
      <SectionNav section="today" />
      <ProductionPlanPanel />
      <div className="section-heading">
        <div>
          <h2>接下来，处理这些</h2>
          <p>包含之前未完成的任务与作品</p>
        </div>
        <Link to="/drafts">
          全部作品 <ArrowRightOutlined />
        </Link>
      </div>
      {(tasks.isLoading || drafts.isLoading) && <LoadingBlock rows={4} />}
      {tasks.isError && (
        <ErrorState error={tasks.error} onRetry={() => void tasks.refetch()} />
      )}
      {drafts.isError && (
        <ErrorState
          error={drafts.error}
          onRetry={() => void drafts.refetch()}
        />
      )}
      {attention.length > 0 && (
        <section className="work-surface action-section">
          <h3>
            需要你处理 <span>{attention.length}</span>
          </h3>
          <TaskRows tasks={attention.slice(0, 5)} />
          {attention.length > 5 && <Link to="/tasks">查看全部待处理任务</Link>}
        </section>
      )}
      {waiting.length > 0 && (
        <section className="work-surface action-section">
          <h3>
            等待检查的作品 <span>{waiting.length}</span>
          </h3>
          <div className="action-list">
            {waiting.slice(0, 5).map((draft) => (
              <div className="action-row" key={draft.id}>
                <div>
                  <Link
                    className="action-title"
                    to={`/drafts/${draft.id}/review`}
                  >
                    {draft.title}
                  </Link>
                  <p>
                    文章 v{draft.current_version} ·{" "}
                    {formatDateTime(draft.updated_at, true)}
                  </p>
                </div>
                <Link
                  className="primary-link"
                  to={`/drafts/${draft.id}/review`}
                >
                  检查作品 <ArrowRightOutlined />
                </Link>
              </div>
            ))}
          </div>
          {waiting.length > 5 && <Link to="/drafts">查看全部待检查作品</Link>}
        </section>
      )}
      {tasks.data && drafts.data && !attention.length && !waiting.length && (
        <div className="calm-empty">
          <CheckCircleOutlined />
          <h3>暂时没有需要处理的内容</h3>
          <p>
            {running.length
              ? "作品正在生成，完成后会出现在这里。"
              : "开始今日计划，或先去选题里添加一个问题。"}
          </p>
        </div>
      )}
      {running.length > 0 && (
        <section className="work-surface action-section">
          <h3>
            正在生成 <span>{running.length}</span>
          </h3>
          <TaskRows tasks={running.slice(0, 5)} />
          {running.length > 5 && <Link to="/tasks">查看全部运行任务</Link>}
        </section>
      )}
      {summary.isError && (
        <ErrorState
          error={summary.error}
          onRetry={() => void summary.refetch()}
        />
      )}
      {summary.data && (
        <Collapse
          className="system-details"
          ghost
          items={[
            {
              key: "system",
              label: healthy
                ? "服务已就绪 · 查看运行详情"
                : "服务需要检查 · 查看运行详情",
              children: (
                <>
                  <InfrastructureHealth summary={summary.data} />
                  <h3>最近动态</h3>
                  <ul className="compact-logs">
                    {summary.data.recent_logs.map((log) => (
                      <li key={log.id}>
                        <time>{formatDateTime(log.created_at)}</time>
                        {log.message}
                      </li>
                    ))}
                  </ul>
                  <Link to="/tasks">完整任务记录</Link>
                </>
              ),
            },
          ]}
        />
      )}
    </div>
  );
}
