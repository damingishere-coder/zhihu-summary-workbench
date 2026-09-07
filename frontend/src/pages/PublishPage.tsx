import {
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  FileProtectOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Calendar,
  Input,
  Modal,
  Radio,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
} from "antd";
import type { Dayjs } from "dayjs";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ProductionPlanPanel } from "../components/ProductionPlanPanel";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { Draft, PublishReadiness, PublishSchedule } from "../types";
import { formatDateTime } from "../utils/format";

type ReadyRow = Draft & { readiness: PublishReadiness };

function localDateTimeTomorrow() {
  const value = new Date(Date.now() + 24 * 60 * 60 * 1000);
  value.setMinutes(0, 0, 0);
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

export function PublishPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [scheduleDraft, setScheduleDraft] = useState<ReadyRow | null>(null);
  const [scheduledFor, setScheduledFor] = useState(localDateTimeTomorrow);
  const [mode, setMode] = useState<"manual" | "assisted">("manual");
  const [executeSchedule, setExecuteSchedule] = useState<PublishSchedule | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const readiness = useQuery({
    queryKey: ["drafts", "publish-readiness"],
    queryFn: async () => {
      const drafts = await api.drafts();
      const rows = await Promise.all(
        drafts.items.map(async (draft) => ({
          ...draft,
          readiness: await api.publishReadiness(draft.id),
        })),
      );
      return rows;
    },
  });
  const schedules = useQuery({ queryKey: ["publish-schedules"], queryFn: api.publishSchedules });
  const records = useQuery({ queryKey: ["publish-records"], queryFn: api.publishRecords });
  const plan = useQuery({ queryKey: ["daily-plan"], queryFn: api.todayPlan });
  const usage = useQuery({ queryKey: ["model-usage"], queryFn: api.modelUsage });
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["publish-schedules"] }),
      queryClient.invalidateQueries({ queryKey: ["publish-records"] }),
      queryClient.invalidateQueries({ queryKey: ["drafts", "publish-readiness"] }),
      queryClient.invalidateQueries({ queryKey: ["daily-plan"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  };
  const create = useMutation({
    mutationFn: () => api.createPublishSchedule({
      article_draft_id: scheduleDraft!.id,
      scheduled_for: new Date(scheduledFor).toISOString(),
      mode,
    }),
    onSuccess: async () => {
      message.success("排期已创建，并冻结当前文章和图片版本");
      setScheduleDraft(null);
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const reschedule = useMutation({
    mutationFn: ({ item, day }: { item: PublishSchedule; day: Dayjs }) => {
      const previous = new Date(item.scheduled_for);
      const target = day.hour(previous.getHours()).minute(previous.getMinutes()).second(0);
      return api.updatePublishSchedule(item.id, { scheduled_for: target.toISOString() });
    },
    onSuccess: async () => {
      message.success("排期已移动");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const execute = useMutation({
    mutationFn: () => api.executePublishSchedule(executeSchedule!.id, confirmation),
    onSuccess: async (record) => {
      message.success(record.status === "paused" ? "已安全暂停并记录原因" : "发布包已准备，等待人工操作");
      setExecuteSchedule(null);
      setConfirmation("");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const runPlan = useMutation({
    mutationFn: api.runTodayPlan,
    onSuccess: async (result) => {
      message.success(result.message);
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });

  const schedulesByDay = useMemo(() => {
    const groups = new Map<string, PublishSchedule[]>();
    schedules.data?.forEach((item) => {
      const key = new Date(item.scheduled_for).toLocaleDateString("zh-CN");
      groups.set(key, [...(groups.get(key) ?? []), item]);
    });
    return groups;
  }, [schedules.data]);

  const contentColumns = [
    {
      title: "内容",
      dataIndex: "title",
      key: "title",
      ellipsis: true,
      render: (value: string, row: ReadyRow) => (
        <div className="table-title">
          <Link to={`/drafts/${row.id}/review`}>{value}</Link>
          <small>{row.question_title}</small>
        </div>
      ),
    },
    {
      title: "文章",
      key: "article",
      width: 120,
      render: (_: unknown, row: ReadyRow) => (
        <Tag color={row.readiness.article_approved ? "success" : "warning"}>
          {row.readiness.article_approved ? `已审核 v${row.readiness.article_version}` : "待审核"}
        </Tag>
      ),
    },
    {
      title: "信息图",
      key: "image",
      width: 120,
      render: (_: unknown, row: ReadyRow) => (
        <Tag color={row.readiness.image_rendered ? "success" : "default"}>
          {row.readiness.image_rendered ? `已渲染 v${row.readiness.image_version}` : "待渲染"}
        </Tag>
      ),
    },
    {
      title: "风险",
      key: "risk",
      width: 105,
      render: (_: unknown, row: ReadyRow) => (
        <Tag icon={<FileProtectOutlined />} color={row.readiness.risk_level === "high" ? "error" : "default"}>
          {row.readiness.risk_level}
        </Tag>
      ),
    },
    {
      title: "准备状态",
      key: "ready",
      width: 210,
      render: (_: unknown, row: ReadyRow) =>
        row.readiness.ready ? (
          <Tag color="success" icon={<CheckCircleOutlined />}>可以排期</Tag>
        ) : (
          <span className="publish-blocker">{row.readiness.blockers.join("；")}</span>
        ),
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_: unknown, row: ReadyRow) => (
        <Space><Button size="small" disabled={!row.readiness.ready} href={row.readiness.ready ? api.publishPackageUrl(row.id) : undefined}>下载发布包</Button><Button size="small" type="primary" disabled={!row.readiness.ready} onClick={() => setScheduleDraft(row)}>
          加入排期
        </Button></Space>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="发布中心"
        description="先冻结审核通过的文章与已渲染信息图，再排期、确认并进入人工或浏览器辅助发布。"
        actions={<Button icon={<PlayCircleOutlined />} loading={runPlan.isPending} onClick={() => runPlan.mutate()}>立即执行今日计划</Button>}
      />
      <Alert
        className="phase-alert"
        type="info"
        showIcon
        icon={<SafetyCertificateOutlined />}
        title="人工审核与发布"
        description="审核通过后下载文章、信息图和来源组成的发布包；在知乎完成最后发布。工作台不会自动发布。"
      />
      <ProductionPlanPanel />
      <div className="publish-stat-strip">
        <Statistic title="今日计划" value={plan.data?.question_limit ?? 0} suffix="题" prefix={<ClockCircleOutlined />} />
        <Statistic title="今日模型调用" value={usage.data?.calls ?? 0} suffix="次" />
        <Statistic title="估算费用" value={usage.data?.cost_known === false ? "未知（Codex 额度）" : usage.data?.estimated_cost ?? 0} precision={4} prefix={<DollarOutlined />} />
        <Statistic title="手动生图 Prompt" value={usage.data?.manual_image_generations ?? 0} suffix="次" />
      </div>
      <section className="work-surface publish-workspace">
        <Tabs
          items={[
            {
              key: "content",
              label: "内容准备",
              children: readiness.isLoading ? <LoadingBlock rows={8} /> : readiness.isError ? (
                <ErrorState error={readiness.error} onRetry={() => void readiness.refetch()} />
              ) : (
                <Table<ReadyRow>
                  rowKey="id"
                  columns={contentColumns}
                  dataSource={readiness.data}
                  pagination={{ pageSize: 10, hideOnSinglePage: true }}
                  locale={{ emptyText: "暂无草稿" }}
                />
              ),
            },
            {
              key: "calendar",
              label: <><CalendarOutlined /> 发布日历</>,
              children: (
                <Calendar
                  className="publish-calendar"
                  cellRender={(day) => {
                    const items = schedulesByDay.get(day.toDate().toLocaleDateString("zh-CN")) ?? [];
                    return (
                      <div
                        className="publish-calendar-cell"
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => {
                          const id = event.dataTransfer.getData("text/schedule-id");
                          const item = schedules.data?.find((value) => value.id === id);
                          if (item) reschedule.mutate({ item, day });
                        }}
                      >
                        {items.map((item) => (
                          <button
                            type="button"
                            key={item.id}
                            className="publish-calendar-item"
                            draggable
                            onDragStart={(event) => event.dataTransfer.setData("text/schedule-id", item.id)}
                            onClick={() => setExecuteSchedule(item)}
                          >
                            <span>{new Date(item.scheduled_for).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</span>
                            <b>{item.article_title}</b>
                            <StatusTag status={item.status} />
                          </button>
                        ))}
                      </div>
                    );
                  }}
                />
              ),
            },
            {
              key: "records",
              label: `发布记录 ${records.data?.length ?? 0}`,
              children: (
                <Table
                  rowKey="id"
                  dataSource={records.data}
                  columns={[
                    { title: "时间", dataIndex: "created_at", width: 160, render: (value: string) => formatDateTime(value, true) },
                    { title: "状态", dataIndex: "status", width: 180, render: (value: string) => <StatusTag status={value} /> },
                    { title: "文章版本", dataIndex: "article_version_id", ellipsis: true },
                    { title: "图片版本", dataIndex: "image_version_id", ellipsis: true },
                    { title: "错误/暂停原因", dataIndex: "error_message", render: (value: string | null) => value || "—" },
                  ]}
                  pagination={{ pageSize: 10, hideOnSinglePage: true }}
                  locale={{ emptyText: "暂无发布记录" }}
                />
              ),
            },
          ]}
        />
      </section>

      <Modal
        title="创建发布排期"
        open={Boolean(scheduleDraft)}
        okText="冻结版本并排期"
        confirmLoading={create.isPending}
        onOk={() => create.mutate()}
        onCancel={() => setScheduleDraft(null)}
      >
        <p><strong>{scheduleDraft?.title}</strong></p>
        <label className="modal-field-label" htmlFor="publish-time">发布时间</label>
        <Input id="publish-time" type="datetime-local" value={scheduledFor} onChange={(event) => setScheduledFor(event.target.value)} />
        <label className="modal-field-label">发布模式</label>
        <Radio.Group value={mode} onChange={(event) => setMode(event.target.value)}>
          <Radio value="manual">人工发布包（推荐）</Radio>
          <Radio value="assisted">浏览器辅助（仍需人工复核）</Radio>
        </Radio.Group>
      </Modal>

      <Modal
        title="发布前最终确认"
        open={Boolean(executeSchedule)}
        okText="确认并准备发布"
        okButtonProps={{ disabled: confirmation !== "确认发布" }}
        confirmLoading={execute.isPending}
        onOk={() => execute.mutate()}
        onCancel={() => {
          setExecuteSchedule(null);
          setConfirmation("");
        }}
      >
        <Alert type="warning" showIcon title="这是有外部影响的操作" description="系统已冻结文章与图片版本。请输入“确认发布”；辅助模式仍会在登录、验证码或风控处暂停。" />
        <label className="modal-field-label" htmlFor="publish-confirmation">确认文字</label>
        <Input id="publish-confirmation" value={confirmation} placeholder="确认发布" onChange={(event) => setConfirmation(event.target.value)} />
        {executeSchedule && (
          <Space className="publish-frozen-versions" wrap>
            <Tag>文章 v{executeSchedule.article_version ?? "—"}</Tag>
            <Tag>图片 v{executeSchedule.image_version ?? "—"}</Tag>
            <Tag>{executeSchedule.mode === "manual" ? "人工模式" : "浏览器辅助"}</Tag>
          </Space>
        )}
      </Modal>
    </div>
  );
}
