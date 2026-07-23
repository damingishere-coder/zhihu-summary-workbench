import {
  App,
  Button,
  Input,
  Select,
  Space,
  Table,
} from "antd";
import { SearchOutlined, UnorderedListOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { ActivityRail } from "../components/ActivityRail";
import { InfrastructureHealth } from "../components/InfrastructureHealth";
import { MetricStrip } from "../components/MetricStrip";
import { PageHeader } from "../components/PageHeader";
import { ProgressCell } from "../components/ProgressCell";
import {
  AddQuestionButton,
  AddQuestionModal,
  ImportQuestionsButton,
  ImportQuestionsModal,
} from "../components/QuestionModals";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { Task } from "../types";
import { formatDateTime, truncateId } from "../utils/format";

export function DashboardPage() {
  const navigate = useNavigate();
  const [addOpen, setAddOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    refetchInterval: 15_000,
  });
  const filtered = useMemo(
    () =>
      (query.data?.recent_tasks ?? []).filter(
        (task) =>
          (!status || task.status === status) &&
          (!search || task.question_title.toLowerCase().includes(search.toLowerCase())),
      ),
    [query.data?.recent_tasks, search, status],
  );
  const columns = [
    {
      title: "问题标题",
      dataIndex: "question_title",
      key: "question_title",
      ellipsis: true,
      render: (value: string, task: Task) => (
        <button className="table-link table-title" onClick={() => navigate(`/questions/${task.question_id}`)}>
          <span>{value}</span>
          <small>ID: {truncateId(task.question_id)}</small>
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
      width: 130,
      render: (value: number) => <ProgressCell progress={value} />,
    },
    {
      title: "Worker",
      dataIndex: "worker_id",
      key: "worker_id",
      width: 130,
      responsive: ["xl" as const],
      render: (value: string | null) => value || "未分配",
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 92,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (value: string) => <StatusTag status={value} />,
    },
  ];

  return (
    <div className="page page--dashboard">
      <PageHeader
        title="仪表盘"
        description="今天的任务、基础设施和模型状态都在这里。"
        actions={
          <Space wrap>
            <AddQuestionButton onClick={() => setAddOpen(true)} />
            <ImportQuestionsButton onClick={() => setImportOpen(true)} />
            <Button icon={<UnorderedListOutlined />} onClick={() => navigate("/tasks")}>
              查看全部任务
            </Button>
          </Space>
        }
      />
      {query.isLoading && <LoadingBlock rows={12} />}
      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {query.data && (
        <div className="dashboard-workbench">
          <div className="dashboard-main">
            <MetricStrip metrics={query.data.metrics} />
            <InfrastructureHealth summary={query.data} />
            <section className="work-surface">
              <div className="table-toolbar">
                <Select
                  value={status}
                  onChange={setStatus}
                  aria-label="任务状态"
                  options={[
                    { value: "", label: "状态：全部" },
                    { value: "queued", label: "队列中" },
                    { value: "extracting_claims", label: "观点提取" },
                    { value: "waiting_review", label: "待审核" },
                    { value: "failed", label: "失败" },
                  ]}
                />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  prefix={<SearchOutlined />}
                  allowClear
                  placeholder="搜索问题标题"
                  className="table-search"
                />
              </div>
              <Table<Task>
                rowKey="id"
                size="middle"
                columns={columns}
                dataSource={filtered}
                pagination={{ pageSize: 8, hideOnSinglePage: true }}
                locale={{ emptyText: "还没有任务。添加问题并加入任务后会显示在这里。" }}
                onRow={(record) => ({
                  onDoubleClick: () => navigate(`/questions/${record.question_id}`),
                })}
              />
            </section>
          </div>
          <ActivityRail logs={query.data.recent_logs} />
        </div>
      )}
      <AddQuestionModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={(id) => navigate(`/questions/${id}`)}
      />
      <ImportQuestionsModal open={importOpen} onClose={() => setImportOpen(false)} />
    </div>
  );
}
