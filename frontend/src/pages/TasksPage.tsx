import { SearchOutlined, MoreOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Descriptions,
  Drawer,
  Dropdown,
  Input,
  Progress,
  Select,
  Space,
  Table,
  Timeline,
} from "antd";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { allTasks } from "../api/collections";
import { useListLocation } from "../hooks/useListLocation";
import { UsageDetails } from "../components/UsageDetails";
import { SectionNav } from "../components/SectionNav";
import { taskAction } from "../utils/taskActions";
import { PageHeader } from "../components/PageHeader";
import { ProgressCell } from "../components/ProgressCell";
import { EmptyState, ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { Task } from "../types";
import { formatDateTime, formatDuration, truncateId } from "../utils/format";

const cancellableStatuses = [
  "queued",
  "fetching_question",
  "fetching_answers",
  "cleaning_answers",
  "evaluating_answers",
  "extracting_claims",
  "generating_embeddings",
  "clustering_claims",
  "refining_clusters",
  "generating_opinion_map",
  "generating_article",
  "reviewing_article",
  "waiting_browser",
  "waiting_login",
  "waiting_verification",
];

export function TasksPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const list = useListLocation();
  const status = list.get("status");
  const search = list.get("search");
  const setStatus = (value: string) => list.set("status", value);
  const setSearch = (value: string) => list.set("search", value);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["tasks", status],
    queryFn: () => allTasks(status),
    refetchInterval: 8_000,
  });
  const detail = useQuery({
    queryKey: ["tasks", selectedId],
    queryFn: () => api.task(selectedId!),
    enabled: Boolean(selectedId),
    refetchInterval: (query) =>
      cancellableStatuses.includes(query.state.data?.status ?? "")
        ? 2_000
        : false,
  });
  const filtered = useMemo(
    () =>
      (query.data?.items ?? []).filter(
        (task) =>
          !search ||
          task.question_title.toLowerCase().includes(search.toLowerCase()),
      ),
    [query.data?.items, search],
  );
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["tasks"] });
    await queryClient.invalidateQueries({ queryKey: ["questions"] });
    await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const retry = useMutation({
    mutationFn: api.retryTask,
    onSuccess: async () => {
      message.success("任务已重新入队");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });

  const cancel = useMutation({
    mutationFn: api.cancelTask,
    onSuccess: async () => {
      message.success("取消请求已提交");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });

  const columns = [
    {
      title: "任务 / 问题",
      key: "task",
      ellipsis: false,
      render: (_: unknown, task: Task) => (
        <button
          className="table-link table-title"
          onClick={() => setSelectedId(task.id)}
        >
          <span>{task.question_title}</span>
          <small>任务 {truncateId(task.id)} · 内容生产流水线</small>
        </button>
      ),
    },
    {
      title: "当前阶段",
      responsive: ["xl" as const],
      dataIndex: "stage",
      key: "stage",
      width: 130,
      render: (value: string) => <StatusTag status={value} />,
    },
    {
      title: "进度",
      responsive: ["lg" as const],
      dataIndex: "progress",
      key: "progress",
      width: 140,
      render: (value: number) => <ProgressCell progress={value} />,
    },
    {
      title: "开始时间",
      dataIndex: "started_at",
      key: "started_at",
      width: 150,
      responsive: ["xxl" as const],
      render: (value: string | null) => formatDateTime(value, true),
    },
    {
      title: "耗时",
      key: "duration",
      width: 100,
      responsive: ["xxl" as const],
      render: (_: unknown, task: Task) =>
        formatDuration(task.started_at, task.completed_at),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 108,
      render: (value: string) => <StatusTag status={value} />,
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      fixed: "right" as const,
      render: (_: unknown, task: Task) => (
        <Space size={8} wrap>
          <Link to={taskAction(task).href}>{taskAction(task).label}</Link>
          <Button
            type="text"
            aria-label="查看任务详情"
            onClick={() => setSelectedId(task.id)}
          >
            详情
          </Button>
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                {
                  key: "retry",
                  label: "重新入队",
                  disabled:
                    !["failed", "cancelled"].includes(task.status) ||
                    retry.isPending,
                  onClick: () => retry.mutate(task.id),
                },
                {
                  key: "cancel",
                  label: "取消任务",
                  danger: true,
                  disabled:
                    !cancellableStatuses.includes(task.status) ||
                    cancel.isPending,
                  onClick: () =>
                    modal.confirm({
                      title: "确认取消任务？",
                      content: "当前步骤结束后停止，已保存的数据会保留。",
                      okText: "确认取消",
                      cancelText: "继续执行",
                      okButtonProps: { danger: true },
                      onOk: () => cancel.mutateAsync(task.id),
                    }),
                },
              ],
            }}
          >
            <Button
              type="text"
              icon={<MoreOutlined />}
              aria-label="更多任务操作"
            />
          </Dropdown>
        </Space>
      ),
    },
  ];

  const selected = detail.data;
  return (
    <div className="page">
      <PageHeader
        title="任务记录"
        description="查看生成进度，处理暂停与异常。"
      />
      <SectionNav section="today" />
      <section className="work-surface">
        <div className="table-toolbar">
          <Select
            value={status}
            onChange={setStatus}
            options={[
              { value: "", label: "状态：全部" },
              { value: "queued", label: "队列中" },
              { value: "fetching_answers", label: "采集回答" },
              { value: "waiting_browser", label: "等待 Chrome 扩展" },
              { value: "waiting_login", label: "等待知乎登录" },
              { value: "waiting_verification", label: "等待人工验证" },
              { value: "extracting_claims", label: "观点提取" },
              { value: "refining_clusters", label: "聚类修正" },
              { value: "generating_article", label: "生成文章" },
              { value: "waiting_review", label: "待审核" },
              { value: "failed", label: "失败" },
              { value: "cancelled", label: "已取消" },
            ]}
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索所属问题"
            className="table-search table-search--wide"
          />
        </div>
        {query.isLoading && <LoadingBlock rows={10} />}
        {query.isError && (
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
          />
        )}
        {query.data && query.data.total === 0 && (
          <EmptyState
            title="还没有任务"
            description="先到问题池添加问题并点击“加入任务”。"
          />
        )}
        {query.data && query.data.total > 0 && (
          <Table<Task>
            rowKey="id"
            columns={columns}
            dataSource={filtered}
            className="comfortable-table"
            pagination={{
              current: Math.min(
                list.page,
                Math.max(1, Math.ceil(filtered.length / 12)),
              ),
              onChange: (page) => list.set("page", page),
              showSizeChanger: false,
              pageSize: 12,
              showTotal: (total) => `共 ${total} 个任务`,
            }}
          />
        )}
      </section>
      <UsageDetails />
      <Drawer
        title="任务详情"
        open={Boolean(selectedId)}
        onClose={() => setSelectedId(null)}
        size={560}
      >
        {detail.isLoading && <LoadingBlock rows={10} />}
        {detail.isError && (
          <ErrorState
            error={detail.error}
            onRetry={() => void detail.refetch()}
          />
        )}
        {selected && (
          <div className="task-drawer">
            <div className="task-drawer__title">
              <div>
                <small>任务 {truncateId(selected.id)}</small>
                <h2>{selected.question_title}</h2>
              </div>
              <StatusTag status={selected.status} />
            </div>
            <Progress
              percent={selected.progress}
              status={
                selected.status === "failed"
                  ? "exception"
                  : selected.progress === 100
                    ? "success"
                    : "active"
              }
            />
            {selected.error_message && (
              <Alert
                className="drawer-alert"
                type="error"
                showIcon
                title="任务失败"
                description={selected.error_message}
              />
            )}
            <Descriptions column={2} size="small">
              <Descriptions.Item label="当前阶段">
                <StatusTag status={selected.stage} />
              </Descriptions.Item>
              <Descriptions.Item label="Worker">
                {selected.worker_id || "未分配"}
              </Descriptions.Item>
              <Descriptions.Item label="开始时间">
                {formatDateTime(selected.started_at, true)}
              </Descriptions.Item>
              <Descriptions.Item label="耗时">
                {formatDuration(selected.started_at, selected.completed_at)}
              </Descriptions.Item>
              <Descriptions.Item label="重试次数">
                {selected.retry_count} / {selected.max_retries}
              </Descriptions.Item>
              <Descriptions.Item label="Provider">
                {selected.result.provider || "等待调用"}
              </Descriptions.Item>
            </Descriptions>
            <h3>完整任务日志</h3>
            <Timeline
              items={selected.logs.map((log) => ({
                color:
                  log.level === "error"
                    ? "red"
                    : log.level === "warning"
                      ? "orange"
                      : "blue",
                content: (
                  <div className="task-log-item">
                    <time>{formatDateTime(log.created_at, true)}</time>
                    <p>{log.message}</p>
                    <small>{log.stage}</small>
                  </div>
                ),
              }))}
            />
          </div>
        )}
      </Drawer>
    </div>
  );
}
