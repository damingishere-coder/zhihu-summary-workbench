import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, InputNumber, Progress, Space } from "antd";
import {
  ArrowRightOutlined,
  PauseOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { StatusTag } from "./StatusTag";
import { runningStatuses } from "../utils/taskActions";

export function ProductionPlanPanel() {
  const { message } = App.useApp();
  const client = useQueryClient();
  const [target, setTarget] = useState<number | null>(null);
  const plan = useQuery({
    queryKey: ["daily-plan"],
    queryFn: api.todayPlan,
    refetchInterval: 5000,
  });
  const refresh = async () => {
    await Promise.all(
      ["daily-plan", "dashboard", "tasks"].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    );
  };
  const run = useMutation({
    mutationFn: api.runTodayPlan,
    onSuccess: async (result) => {
      message.info(result.message);
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const pause = useMutation({
    mutationFn: api.pauseTodayPlan,
    onSuccess: async (result) => {
      message.info(result.message);
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const save = useMutation({
    mutationFn: (limit: number) =>
      api.updateTodayPlan({
        question_limit: limit,
        hot_quota: Math.ceil(limit * 0.6),
        manual_quota: Math.floor(limit * 0.4),
      }),
    onSuccess: async () => {
      setTarget(null);
      await refresh();
      message.success("今日目标已保存");
    },
    onError: (error) => message.error(error.message),
  });
  const result = plan.data?.result ?? {};
  const items = (result.items ?? []) as Array<{
    task_id: string;
    status: string;
  }>;
  const warnings =
    (result.hot_sync as { warnings?: string[] } | undefined)?.warnings ?? [];
  const running = items.some((item) => runningStatuses.includes(item.status));
  const completed = plan.data?.status === "completed";
  const limit = plan.data?.question_limit ?? 10;
  const changed = target !== null && target !== limit;
  const busy = run.isPending || pause.isPending || save.isPending;
  const shortfall = Number(
    result.shortfall ?? Math.max(0, limit - items.length),
  );
  return (
    <section className="plan-surface" aria-label="今日生产计划">
      <div className="plan-heading">
        <div>
          <h2>今日创作计划</h2>
          <p>先启动计划，再回来检查作品。最后由你在知乎发布。</p>
        </div>
        {plan.data && <StatusTag status={plan.data.status} />}
      </div>
      {plan.isLoading && <p role="status">正在读取今日计划…</p>}
      {plan.isError && (
        <Alert
          type="error"
          title={plan.error.message}
          action={<Button onClick={() => void plan.refetch()}>重新加载</Button>}
        />
      )}
      <div className="plan-controls">
        <Space wrap>
          <label htmlFor="daily-target">今日目标</label>
          <InputNumber
            id="daily-target"
            aria-label="今日目标题数"
            min={1}
            max={50}
            precision={0}
            value={target ?? limit}
            disabled={!plan.data || busy || items.length > 0}
            onChange={(value) => setTarget(value ?? limit)}
          />
          <span>题</span>
          {changed && (
            <Button
              loading={save.isPending}
              disabled={busy || !target}
              onClick={() => target && save.mutate(target)}
            >
              保存目标
            </Button>
          )}
        </Space>
        <Space wrap>
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            loading={run.isPending}
            disabled={!plan.data || busy || changed || running || completed}
            onClick={() => run.mutate()}
          >
            {completed
              ? "今日计划已完成"
              : running
                ? "正在生成作品"
                : items.length || plan.data?.status === "paused"
                  ? "继续计划"
                  : "开始今日计划"}
          </Button>
          {(running || run.isPending) && (
            <Button
              icon={<PauseOutlined />}
              loading={pause.isPending}
              disabled={pause.isPending || plan.data?.status === "paused"}
              onClick={() => pause.mutate()}
            >
              暂停计划
            </Button>
          )}
        </Space>
      </div>
      <Progress
        percent={Math.min(
          100,
          Math.round((Number(result.completed ?? 0) / limit) * 100),
        )}
        showInfo={false}
      />
      <div className="plan-counts">
        <span>
          <b>{items.length}</b> / {limit} 已安排
        </span>
        <span>
          <b>{Number(result.article_completed ?? 0)}</b> 文章完成
        </span>
        <span>
          <b>{Number(result.completed ?? 0)}</b> 图文完成
        </span>
        <span>
          <b>{Number(result.waiting ?? 0)}</b> 等待处理
        </span>
        <span>
          <b>{Number(result.failed ?? 0)}</b> 失败或待核对
        </span>
      </div>
      {shortfall > 0 && (
        <div className="plan-hint">
          还可安排 {shortfall} 个选题。
          <Link to="/questions">
            去补充选题 <ArrowRightOutlined />
          </Link>
        </div>
      )}
      {warnings.length > 0 && (
        <Alert type="warning" showIcon title={warnings.join("；")} />
      )}
      {plan.data?.status === "paused" && running && (
        <p role="status">暂停请求已记录，正在等待当前步骤结束。</p>
      )}
    </section>
  );
}
