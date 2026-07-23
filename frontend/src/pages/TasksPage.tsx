import {
  CloseCircleOutlined,
  EyeOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Descriptions,
  Drawer,
  Input,
  Progress,
  Select,
  Space,
  Table,
  Timeline,
  Tooltip,
} from "antd";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ProgressCell } from "../components/ProgressCell";
import { EmptyState, ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { Task } from "../types";
import { formatDateTime, formatDuration, truncateId } from "../utils/format";

export function TasksPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["tasks", status],
    queryFn: () => api.tasks({ status }),
    refetchInterval: 8_000,
  });
  const detail = useQuery({
    queryKey: ["tasks", selectedId],
    queryFn: () => api.task(selectedId!),
    enabled: Boolean(selectedId),
    refetchInterval: (query) =>
      ["queued", "extracting_claims"].includes(query.state.data?.status ?? "") ? 2_000 : false,
  });
  const filtered = useMemo(
    () =>
      (query.data?.items ?? []).filter(
        (task) =>
          !search || task.question_title.toLowerCase().includes(search.toLowerCase()),
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
      ellipsis: true,
      render: (_: unknown, task: Task) => (
        <button className="table-link table-title" onClick={() => setSelectedId(task.id)}>
          <span>{task.question_title}</span>
          <small>任务 {truncateId(task.id)} · 观点提取</small>
        </button>
      ),
    },
    {
      title: "当前阶段",
      dataIndex: "stage",
      key: "stage",
      width: 130,
      render: (value: string) => <StatusTag status={value} />,
    },
    {
      title: "进度",
      dataIndex: "progress",
      key: "progress",
      width: 140,
      render: (value: number) => <ProgressCell progress={value} />,
    },
    {
      title: "开始时间",
      dataIndex: "started_at",
      key: "started_at",
      width: 120,
      responsive: ["xl" as const],
      render: (value: string | null) => formatDateTime(value, true),
    },
    {
      title: "耗时",
      key: "duration",
      width: 100,
      responsive: ["xl" as const],
      render: (_: unknown, task: Task) => formatDuration(task.started_at, task.completed_at),
    },
    {
      title: "Worker",
      dataIndex: "worker_id",
      key: "worker_id",
      width: 130,
      render: (value: string | null) => value ? truncateId(value) : "等待分配",
    },
    {
      title: "重试",
      dataIndex: "retry_count",
      key: "retry_count",
      width: 72,
      render: (value: number, task: Task) => `${value}/${task.max_retries}`,
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
      width: 120,
      fixed: "right" as const,
      render: (_: unknown, task: Task) => (
        <Space size={2}>
          <Tooltip title="查看任务详情和完整日志">
            <Button type="text" aria-label="查看任务详情" icon={<EyeOutlined />} onClick={() => setSelectedId(task.id)} />
          </Tooltip>
          <Tooltip title={["failed", "cancelled"].includes(task.status) ? "重新入队" : "当前状态不能重试"}>
            <Button
              type="text"
              aria-label="重试任务"
              icon={<ReloadOutlined />}
              disabled={!["failed", "cancelled"].includes(task.status)}
              onClick={() => retry.mutate(task.id)}
            />
          </Tooltip>
          <Tooltip title={["queued", "extracting_claims"].includes(task.status) ? "取消任务" : "当前状态不能取消"}>
            <Button
              type="text"
              danger
              aria-label="取消任务"
              icon={<CloseCircleOutlined />}
              disabled={!["queued", "extracting_claims"].includes(task.status)}
              onClick={() =>
                modal.confirm({
                  title: "确认取消任务？",
                  content: "运行中的模型调用会先结束，但结果不会写入草稿。",
                  okText: "确认取消",
                  okButtonProps: { danger: true },
                  cancelText: "继续执行",
                  onOk: () => cancel.mutateAsync(task.id),
                })
              }
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const selected = detail.data;
  return (
    <div className="page">
      <PageHeader title="任务中心" description="跟踪 Worker、任务阶段、实时进度、重试次数和失败原因。" />
      <section className="work-surface">
        <div className="table-toolbar">
          <Select
            value={status}
            onChange={setStatus}
            options={[
              { value: "", label: "状态：全部" },
              { value: "queued", label: "队列中" },
              { value: "extracting_claims", label: "观点提取" },
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
        {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {query.data && query.data.total === 0 && (
          <EmptyState title="还没有任务" description="先到问题池添加问题并点击“加入任务”。" />
        )}
        {query.data && query.data.total > 0 && (
          <Table<Task>
            rowKey="id"
            columns={columns}
            dataSource={filtered}
            scroll={{ x: 1100 }}
            pagination={{ pageSize: 12, showTotal: (total) => `共 ${total} 个任务` }}
          />
        )}
      </section>
      <Drawer
        title="任务详情"
        open={Boolean(selectedId)}
        onClose={() => setSelectedId(null)}
        size={560}
      >
        {detail.isLoading && <LoadingBlock rows={10} />}
        {detail.isError && <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}
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
              status={selected.status === "failed" ? "exception" : selected.progress === 100 ? "success" : "active"}
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
              <Descriptions.Item label="当前阶段"><StatusTag status={selected.stage} /></Descriptions.Item>
              <Descriptions.Item label="Worker">{selected.worker_id || "未分配"}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(selected.started_at, true)}</Descriptions.Item>
              <Descriptions.Item label="耗时">{formatDuration(selected.started_at, selected.completed_at)}</Descriptions.Item>
              <Descriptions.Item label="重试次数">{selected.retry_count} / {selected.max_retries}</Descriptions.Item>
              <Descriptions.Item label="Provider">{selected.result.provider || "等待调用"}</Descriptions.Item>
            </Descriptions>
            <h3>完整任务日志</h3>
            <Timeline
              items={selected.logs.map((log) => ({
                color: log.level === "error" ? "red" : log.level === "warning" ? "orange" : "blue",
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
