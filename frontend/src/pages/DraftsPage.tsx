import { EditOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Table } from "antd";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { Draft } from "../types";
import { formatDateTime } from "../utils/format";

export function DraftsPage() {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["drafts"], queryFn: api.drafts });
  const columns = [
    {
      title: "草稿标题",
      dataIndex: "title",
      key: "title",
      ellipsis: true,
      render: (value: string, draft: Draft) => (
        <button className="table-link table-title" onClick={() => navigate(`/drafts/${draft.id}/review`)}>
          <span>{value}</span>
          <small>来源：{draft.question_title}</small>
        </button>
      ),
    },
    {
      title: "版本",
      dataIndex: "current_version",
      key: "current_version",
      width: 90,
      render: (value: number) => `v${value}`,
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
      width: 150,
      render: (value: string) => formatDateTime(value, true),
    },
    {
      title: "操作",
      key: "action",
      width: 120,
      render: (_: unknown, draft: Draft) => (
        <Button icon={<EditOutlined />} onClick={() => navigate(`/drafts/${draft.id}/review`)}>
          审核
        </Button>
      ),
    },
  ];
  return (
    <div className="page">
      <PageHeader title="草稿审核" description="审核总结文章、段落来源、质量结果和手动图片 Prompt 工作流。" />
      <section className="work-surface">
        {query.isLoading && <LoadingBlock rows={9} />}
        {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {query.data?.total === 0 && (
          <EmptyState
            title="还没有待审核草稿"
            description="问题完成回答采集、观点聚类、文章生成和独立审核后，会自动进入这里。"
          />
        )}
        {query.data && query.data.total > 0 && (
          <Table<Draft>
            rowKey="id"
            columns={columns}
            dataSource={query.data.items}
            pagination={{ pageSize: 12, showTotal: (total) => `共 ${total} 篇` }}
          />
        )}
      </section>
    </div>
  );
}
