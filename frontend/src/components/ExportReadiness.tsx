import { useQuery } from "@tanstack/react-query";
import { Alert, Button } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { api } from "../api/client";
import { ErrorState, LoadingBlock } from "./StateViews";

export function ExportReadiness({
  draftId,
  blocked,
}: {
  draftId: string;
  blocked: boolean;
}) {
  const query = useQuery({
    queryKey: ["publish-readiness", draftId],
    queryFn: () => api.publishReadiness(draftId),
    staleTime: 0,
  });
  return (
    <section className="export-readiness" aria-label="导出检查">
      <h3>准备好后，带走你的作品</h3>
      {query.isLoading && <LoadingBlock rows={2} />}
      {query.isError && (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      )}
      {blocked && <Alert type="info" title="请先保存修改，并完成当前操作" />}
      {query.data && (
        <>
          <ul className="readiness-checks">
            <li>
              {query.data.article_approved
                ? "✓ 文章已通过人工审核"
                : "○ 文章待人工审核"}
            </li>
            <li>
              {query.data.image_rendered
                ? "✓ 配图已生成 PNG"
                : "○ 配图待生成 PNG"}
            </li>
          </ul>
          {query.data.blockers.length > 0 && (
            <Alert
              type="warning"
              title="还需要完成"
              description={
                <ul>
                  {query.data.blockers.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              }
            />
          )}
          {query.data.warnings.length > 0 && (
            <p>{query.data.warnings.join("；")}</p>
          )}
        </>
      )}
      <Button
        type="primary"
        size="large"
        icon={<DownloadOutlined />}
        disabled={
          blocked || query.isFetching || query.isError || !query.data?.ready
        }
        href={
          !blocked && !query.isFetching && !query.isError && query.data?.ready
            ? api.publishPackageUrl(draftId)
            : undefined
        }
      >
        下载发布包
      </Button>
      <p>包含文章、PNG 配图与来源记录。下载后，在知乎完成最后发布。</p>
    </section>
  );
}
