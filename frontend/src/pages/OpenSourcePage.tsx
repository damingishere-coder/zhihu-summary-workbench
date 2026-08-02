import { ExportOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Table, Tag } from "antd";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";

export function OpenSourcePage() {
  const query = useQuery({ queryKey: ["open-source-references"], queryFn: api.openSourceReferences });
  return (
    <div className="page">
      <PageHeader title="开源组件与许可证" description="记录本项目直接使用的开源项目、许可证和用途，便于后续审计。" />
      <section className="work-surface">
        {query.isLoading && <LoadingBlock rows={10} />}
        {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {query.data && (
          <Table
            rowKey="id"
            dataSource={query.data}
            pagination={false}
            columns={[
              {
                title: "项目",
                dataIndex: "name",
                width: 190,
                render: (value: string, item) => <a href={item.source_url} target="_blank" rel="noreferrer">{value} <ExportOutlined /></a>,
              },
              { title: "版本", dataIndex: "version", width: 120 },
              { title: "许可证", dataIndex: "license_name", width: 150, render: (value: string) => <Tag>{value}</Tag> },
              { title: "项目内用途", dataIndex: "usage_note" },
            ]}
          />
        )}
      </section>
    </div>
  );
}
