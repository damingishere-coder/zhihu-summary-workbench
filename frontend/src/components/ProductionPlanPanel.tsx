import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, InputNumber, Space, Statistic, Table } from "antd";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { StatusTag } from "./StatusTag";

interface PlanItem { task_id: string; question_id: string; status: string; stage: string; progress: number; error?: string }

export function ProductionPlanPanel() {
  const { message } = App.useApp();
  const client = useQueryClient();
  const plan = useQuery({ queryKey: ["daily-plan"], queryFn: api.todayPlan, refetchInterval: 5000 });
  const refresh = async () => {
    await Promise.all(["daily-plan", "dashboard", "tasks"].map(key => client.invalidateQueries({ queryKey: [key] })));
  };
  const run = useMutation({ mutationFn: api.runTodayPlan, onSuccess: async result => { message.info(result.message); await refresh(); }, onError: error => message.error(error.message) });
  const pause = useMutation({ mutationFn: api.pauseTodayPlan, onSuccess: async result => { message.info(result.message); await refresh(); }, onError: error => message.error(error.message) });
  const resume = useMutation({ mutationFn: (row: PlanItem) => row.error?.startsWith("资料不足") ? api.continuePartialTask(row.task_id) : api.continueTask(row.task_id), onSuccess: refresh, onError: error => message.error(error.message) });
  const save = useMutation({ mutationFn: (limit: number) => api.updateTodayPlan({ question_limit: limit, hot_quota: Math.ceil(limit * .6), manual_quota: Math.floor(limit * .4) }), onSuccess: refresh, onError: error => message.error(error.message) });
  const result = plan.data?.result ?? {};
  const items = (result.items ?? []) as PlanItem[];
  const warnings = ((result.hot_sync as { warnings?: string[] } | undefined)?.warnings ?? []);
  return <section className="work-surface" style={{ padding: 20, marginBottom: 16 }}>
    <Space wrap style={{ width: "100%", justifyContent: "space-between", marginBottom: 12 }}>
      <Space><strong>今日生产计划</strong>{plan.data && <StatusTag status={plan.data.status} />}</Space>
      <Space wrap>
        <span>目标题数</span><InputNumber aria-label="今日目标题数" min={1} max={50} value={plan.data?.question_limit ?? 10} disabled={save.isPending || run.isPending || items.length > 0} onChange={value => value && save.mutate(value)} />
        <Button type="primary" loading={run.isPending} disabled={!plan.data} onClick={() => run.mutate()}>执行 / 继续今日计划</Button>
        <Button loading={pause.isPending} disabled={!plan.data} onClick={() => pause.mutate()}>暂停计划</Button>
      </Space>
    </Space>
    <p>由 RunDock 手动启动服务。点击执行后才采集、分析和生图；重启后需手动继续。每题最多采集 30 分钟，发布由你审核后操作。</p>
    {plan.isError && <Alert type="error" title={plan.error.message} />}
    {warnings.length > 0 && <Alert type="warning" title={warnings.join("；")} style={{ marginBottom: 12 }} />}
    <Space size="large" wrap>
      <Statistic title="已安排" value={items.length} suffix={`/ ${plan.data?.question_limit ?? 10}`} />
      <Statistic title="文章完成" value={Number(result.article_completed ?? 0)} />
      <Statistic title="图文完成，待审核" value={Number(result.completed ?? 0)} />
      <Statistic title="等待处理" value={Number(result.waiting ?? 0)} />
      <Statistic title="失败 / 结果待核对" value={Number(result.failed ?? 0)} />
      <Statistic title="候选缺口" value={Number(result.shortfall ?? Math.max(0, (plan.data?.question_limit ?? 10) - items.length))} />
    </Space>
    {items.length > 0 && <Table size="small" rowKey="task_id" dataSource={items} pagination={false} style={{ marginTop: 12 }} columns={[
      { title: "任务", render: (_, row) => <Link to={`/questions/${row.question_id}`}>查看问题与结果</Link> },
      { title: "阶段", dataIndex: "stage", render: value => <StatusTag status={value} /> },
      { title: "状态", dataIndex: "status", render: value => <StatusTag status={value} /> },
      { title: "需要处理", dataIndex: "error", render: value => value || "—" },
      { title: "操作", render: (_, row) => ["paused", "failed", "waiting_browser", "waiting_login", "waiting_verification", "image_result_unknown"].includes(row.status) ? <Button size="small" loading={resume.isPending} onClick={() => resume.mutate(row)}>{row.error?.startsWith("资料不足") ? "按现有资料继续" : row.status === "image_result_unknown" ? "核对已有图片并继续" : "继续"}</Button> : null },
    ]} />}
  </section>;
}
