import { FileProtectOutlined, LockOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Steps, Table, Tag } from "antd";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { Draft } from "../types";
import { formatDateTime } from "../utils/format";

export function PublishPage() {
  const query = useQuery({ queryKey: ["drafts", "publish-readiness"], queryFn: api.drafts });
  const columns = [
    {
      title: "内容",
      dataIndex: "title",
      key: "title",
      ellipsis: true,
      render: (value: string, draft: Draft) => (
        <div className="table-title"><span>{value}</span><small>{draft.question_title}</small></div>
      ),
    },
    {
      title: "草稿状态",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (value: string) => <StatusTag status={value} />,
    },
    {
      title: "风险状态",
      key: "risk",
      width: 130,
      render: () => <Tag icon={<FileProtectOutlined />}>待二阶段审核</Tag>,
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 150,
      render: (value: string) => formatDateTime(value, true),
    },
    {
      title: "发布",
      key: "publish",
      width: 130,
      render: () => <Tag icon={<LockOutlined />}>第三阶段启用</Tag>,
    },
  ];
  return (
    <div className="page">
      <PageHeader title="发布中心" description="检查真实内容准备状态；排期和辅助发布将在第三阶段启用。" />
      <Alert
        className="phase-alert"
        type="info"
        showIcon
        icon={<SafetyCertificateOutlined />}
        title="发布功能按阶段安全锁定"
        description="当前只展示数据库中的真实草稿及其准备状态。自动发布默认关闭，第三阶段仍会要求人工审核、登录检查和发布前确认。"
      />
      <section className="work-surface publish-readiness">
        <h2>启用路径</h2>
        <Steps
          current={0}
          items={[
            { title: "第一阶段", content: "架构与最小草稿" },
            { title: "第二阶段", content: "真实来源与质量审核" },
            { title: "第三阶段", content: "信息图、排期与辅助发布" },
          ]}
        />
      </section>
      <section className="work-surface">
        <div className="section-heading">
          <h2>内容准备</h2>
          <span className="section-caption">来自真实数据库 · 不使用静态假数据</span>
        </div>
        {query.isLoading && <LoadingBlock rows={6} />}
        {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {query.data && (
          <Table<Draft>
            rowKey="id"
            columns={columns}
            dataSource={query.data.items}
            locale={{ emptyText: "暂无草稿。完成一个问题任务后，这里会显示真实内容准备状态。" }}
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
          />
        )}
      </section>
    </div>
  );
}
