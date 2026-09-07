import {
  DeleteOutlined,
  EyeOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Dropdown,
  Input,
  Segmented,
  Select,
  Space,
  Table,
  Tooltip,
} from "antd";
import { useMemo, useState } from "react";
import { useListLocation } from "../hooks/useListLocation";
import { useNavigate, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import {
  AddQuestionButton,
  AddQuestionModal,
  ImportQuestionsModal,
} from "../components/QuestionModals";
import { EmptyState, ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { Priority, Question } from "../types";
import { formatDateTime } from "../utils/format";

const tabStatus: Record<string, string> = {
  全部问题: "",
  排队中: "queued",
  待检查: "waiting_review",
  已忽略: "ignored",
};

export const PERMANENT_DELETE_WARNING =
  "将同时删除关联任务、回答、分析、草稿、图片和本地发布记录，删除后无法恢复。此操作不会删除知乎网站上的内容。若任务正在排队或运行，请先取消并等待停止。";

export function QuestionsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const detailUrl = (id: string) =>
    `/questions/${id}?returnTo=${encodeURIComponent(location.pathname + location.search)}`;
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const list = useListLocation();
  const tab = list.get("tab", "全部问题");
  const source = list.get("source");
  const priority = list.get("priority");
  const search = list.get("search");
  const setTab = (value: string) => list.set("tab", value);
  const setSource = (value: string) => list.set("source", value);
  const setPriority = (value: string) => list.set("priority", value);
  const setSearch = (value: string) => list.set("search", value);
  const filters = useMemo(
    () => ({
      status: tabStatus[tab],
      source,
      priority,
      search,
      offset: (list.page - 1) * 12,
      limit: 12,
    }),
    [priority, search, source, tab, list.page],
  );
  const query = useQuery({
    queryKey: ["questions", filters],
    queryFn: () => api.questions(filters),
  });
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["questions"] }),
      queryClient.invalidateQueries({ queryKey: ["tasks"] }),
      queryClient.invalidateQueries({ queryKey: ["drafts"] }),
      queryClient.invalidateQueries({ queryKey: ["publish-schedules"] }),
      queryClient.invalidateQueries({ queryKey: ["publish-records"] }),
      queryClient.invalidateQueries({
        queryKey: ["drafts", "publish-readiness"],
      }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  };
  const queueMutation = useMutation({
    mutationFn: api.queueQuestion,
    onSuccess: async () => {
      message.success("任务已加入队列");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const hotMutation = useMutation({
    mutationFn: api.fetchHotQuestions,
    onSuccess: async (result) => {
      message.info(
        result.warnings?.length
          ? result.warnings.join("；")
          : `热榜已同步：新增 ${result.created}，更新 ${result.updated}`,
      );
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<Question> }) =>
      api.updateQuestion(id, payload),
    onSuccess: refresh,
    onError: (error) => message.error(error.message),
  });
  const ignoreMutation = useMutation({
    mutationFn: api.ignoreQuestion,
    onSuccess: async () => {
      message.success("问题已忽略，可通过“已忽略”标签找回");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: api.deleteQuestion,
    onSuccess: async () => {
      message.success("问题及全部关联本地数据已永久删除");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const columns = [
    {
      title: "问题标题",
      dataIndex: "title",
      key: "title",
      ellipsis: false,
      render: (value: string, question: Question) => (
        <button
          className="table-link table-title"
          onClick={() => navigate(detailUrl(question.id))}
        >
          <span>{value}</span>
          <small>{question.url}</small>
        </button>
      ),
    },
    {
      title: "来源",
      responsive: ["xl" as const],
      dataIndex: "source",
      key: "source",
      width: 100,
      render: (value: string) =>
        ({ manual: "手动推荐", import: "批量导入", hot: "热门问题" })[value] ||
        value,
    },
    {
      title: "优先级",
      responsive: ["xl" as const],
      dataIndex: "priority",
      key: "priority",
      width: 92,
      render: (value: Priority, record: Question) => (
        <Select
          size="small"
          variant="borderless"
          value={value}
          aria-label={`修改 ${record.title} 的优先级`}
          onChange={(next) =>
            updateMutation.mutate({
              id: record.id,
              payload: { priority: next },
            })
          }
          options={[
            { value: "high", label: "高" },
            { value: "medium", label: "中" },
            { value: "low", label: "低" },
          ]}
        />
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (value: string) => <StatusTag status={value} />,
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 120,
      responsive: ["xl" as const],
      render: (value: string) => formatDateTime(value, true),
    },
    {
      title: "操作",
      key: "actions",
      width: 200,
      fixed: "right" as const,
      render: (_: unknown, question: Question) => (
        <Space size={2}>
          <Tooltip
            title={
              question.status === "candidate"
                ? "加入任务"
                : "该问题已有任务记录"
            }
          >
            <Button
              type="text"
              icon={<PlayCircleOutlined />}
              aria-label="加入任务"
              disabled={
                question.status !== "candidate" || queueMutation.isPending
              }
              loading={
                queueMutation.isPending &&
                queueMutation.variables === question.id
              }
              onClick={() => queueMutation.mutate(question.id)}
            >
              开始生成
            </Button>
          </Tooltip>
          <Tooltip title="查看详情">
            <Button
              type="text"
              icon={<EyeOutlined />}
              aria-label="查看详情"
              onClick={() => navigate(detailUrl(question.id))}
            >
              详情
            </Button>
          </Tooltip>
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                {
                  key: "ignore",
                  icon: <StopOutlined />,
                  label: "忽略",
                  disabled: question.status === "ignored",
                  onClick: () => ignoreMutation.mutate(question.id),
                },
                {
                  key: "delete",
                  icon: <DeleteOutlined />,
                  label: "删除",
                  danger: true,
                  onClick: () =>
                    modal.confirm({
                      title: "永久删除这个问题？",
                      content: PERMANENT_DELETE_WARNING,
                      okText: "永久删除",
                      okButtonProps: { danger: true },
                      cancelText: "取消",
                      onOk: () => deleteMutation.mutateAsync(question.id),
                    }),
                },
              ],
            }}
          >
            <Button type="text" icon={<MoreOutlined />} aria-label="更多操作" />
          </Dropdown>
        </Space>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="选题"
        description="从一个值得回答的问题开始。"
        actions={
          <Space wrap>
            <Tooltip title="通过已配对的 Chrome 扩展读取知乎热榜">
              <Button
                loading={hotMutation.isPending}
                onClick={() => hotMutation.mutate()}
              >
                同步知乎热榜
              </Button>
            </Tooltip>
            <AddQuestionButton onClick={() => setAddOpen(true)} />
            <Dropdown
              menu={{
                items: [
                  {
                    key: "import",
                    label: "批量导入",
                    onClick: () => setImportOpen(true),
                  },
                ],
              }}
              trigger={["click"]}
            >
              <Button icon={<MoreOutlined />}>更多</Button>
            </Dropdown>
          </Space>
        }
      />
      <section className="work-surface">
        <div className="question-tabs">
          <Segmented
            value={tab}
            onChange={(value) => setTab(String(value))}
            options={Object.keys(tabStatus)}
          />
        </div>
        <div className="table-toolbar">
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索问题标题或链接"
            className="table-search table-search--wide"
          />
          <Select
            value={source}
            onChange={setSource}
            options={[
              { value: "", label: "来源：全部" },
              { value: "manual", label: "手动推荐" },
              { value: "import", label: "批量导入" },
              { value: "hot", label: "热门问题" },
            ]}
          />
          <Select
            value={priority}
            onChange={setPriority}
            options={[
              { value: "", label: "优先级：全部" },
              { value: "high", label: "高" },
              { value: "medium", label: "中" },
              { value: "low", label: "低" },
            ]}
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
            title="问题池还没有内容"
            description="先添加一个知乎问题，保存后可以设置优先级并加入任务。"
            action={<AddQuestionButton onClick={() => setAddOpen(true)} />}
          />
        )}
        {query.data && query.data.total > 0 && (
          <Table<Question>
            rowKey="id"
            columns={columns}
            dataSource={query.data.items}
            className="comfortable-table"
            pagination={{
              current: list.page,
              onChange: (page) => list.set("page", page),
              showSizeChanger: false,
              pageSize: 12,
              total: query.data.total,
              showTotal: (total) => `共 ${total} 条`,
            }}
          />
        )}
      </section>
      <AddQuestionModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={(id) => navigate(`/questions/${id}`)}
      />
      <ImportQuestionsModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
      />
    </div>
  );
}
