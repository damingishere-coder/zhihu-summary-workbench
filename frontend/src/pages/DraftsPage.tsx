import {
  ArrowRightOutlined,
  FileTextOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Input, Pagination, Segmented } from "antd";
import { Link, useLocation } from "react-router-dom";
import { allDrafts } from "../api/collections";
import { PageHeader } from "../components/PageHeader";
import { SectionNav } from "../components/SectionNav";
import { EmptyState, ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import { useListLocation } from "../hooks/useListLocation";
import { formatDateTime } from "../utils/format";

export function DraftsPage() {
  const list = useListLocation();
  const location = useLocation();
  const query = useQuery({ queryKey: ["drafts", "all"], queryFn: allDrafts });
  const search = list.get("search");
  const status = list.get("status", "all");
  const rows = (query.data?.items ?? []).filter(
    (draft) =>
      (!search ||
        `${draft.title} ${draft.question_title}`
          .toLowerCase()
          .includes(search.toLowerCase())) &&
      (status === "all" ||
        (status === "approved"
          ? draft.status === "review_approved"
          : draft.status !== "review_approved")),
  );
  const page = Math.min(list.page, Math.max(1, Math.ceil(rows.length / 12)));
  return (
    <div className="page">
      <PageHeader
        title="作品"
        description="每一篇，都是从问题到答案的一次整理。"
      />
      <SectionNav section="works" />
      <div className="works-toolbar">
        <Segmented
          aria-label="作品状态"
          value={status}
          onChange={(value) => list.set("status", value)}
          options={[
            { value: "all", label: "全部" },
            { value: "waiting", label: "待检查" },
            { value: "approved", label: "已审核" },
          ]}
        />
        <Input
          aria-label="搜索作品"
          prefix={<SearchOutlined />}
          placeholder="搜索作品或来源问题"
          allowClear
          value={search}
          onChange={(event) => list.set("search", event.target.value)}
        />
      </div>
      {query.isLoading && <LoadingBlock rows={8} />}
      {query.isError && (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      )}
      {query.data && !rows.length && (
        <EmptyState
          title={
            search || status !== "all"
              ? "没有符合条件的作品"
              : "第一篇作品，即将从这里开始"
          }
          description={
            search || status !== "all"
              ? "试试其他关键词，或切回全部作品。"
              : "开始今日计划，生成的文章会来到这里等待你检查。"
          }
          action={<Link to="/dashboard">回到今天</Link>}
        />
      )}
      <div className="works-grid">
        {rows.slice((page - 1) * 12, page * 12).map((draft) => (
          <article className="work-card" key={draft.id}>
            <div className="work-card-meta">
              <span>
                <FileTextOutlined /> 文章 v{draft.current_version}
              </span>
              <StatusTag status={draft.status} />
            </div>
            <h2>
              <Link
                to={`/drafts/${draft.id}/review?returnTo=${encodeURIComponent(location.pathname + location.search)}`}
              >
                {draft.title}
              </Link>
            </h2>
            <p className="work-excerpt">
              {draft.content.replace(/[#>*]/g, "").slice(0, 160)}
            </p>
            <div className="work-card-footer">
              <time>{formatDateTime(draft.updated_at, true)}</time>
              <Link
                to={`/drafts/${draft.id}/review?${draft.status === "review_approved" ? "step=review&" : ""}returnTo=${encodeURIComponent(location.pathname + location.search)}`}
              >
                {draft.status === "review_approved" ? "检查与导出" : "检查作品"}{" "}
                <ArrowRightOutlined />
              </Link>
            </div>
          </article>
        ))}
      </div>
      {rows.length > 12 && (
        <Pagination
          current={page}
          pageSize={12}
          total={rows.length}
          showSizeChanger={false}
          onChange={(page) => list.set("page", page)}
          showTotal={(total) => `共 ${total} 篇`}
        />
      )}
    </div>
  );
}
