import {
  ArrowLeftOutlined,
  CheckOutlined,
  LinkOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Input, Space } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";

function MarkdownPreview({ content }: { content: string }) {
  return (
    <article className="markdown-preview">
      {content.split(/\r?\n/).map((line, index) => {
        if (line.startsWith("# ")) return <h1 key={index}>{line.slice(2)}</h1>;
        if (line.startsWith("## ")) return <h2 key={index}>{line.slice(3)}</h2>;
        if (line.startsWith("- ")) return <li key={index}>{line.slice(2)}</li>;
        if (line.startsWith("> ")) return <blockquote key={index}>{line.slice(2)}</blockquote>;
        return line ? <p key={index}>{line}</p> : <br key={index} />;
      })}
    </article>
  );
}

export function DraftReviewPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["drafts", id], queryFn: () => api.draft(id), enabled: Boolean(id) });
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (query.data) {
      setTitle(query.data.title);
      setContent(query.data.content);
      setDirty(false);
    }
  }, [query.data]);
  const mutation = useMutation({
    mutationFn: () => api.updateDraft(id, { title, content }),
    onSuccess: async (draft) => {
      message.success(`已保存为版本 v${draft.current_version}`);
      setDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
    onError: (error) => message.error(error.message),
  });

  if (query.isLoading) return <div className="page"><LoadingBlock rows={16} /></div>;
  if (query.isError) return <div className="page"><ErrorState error={query.error} onRetry={() => void query.refetch()} /></div>;
  const draft = query.data;
  if (!draft) return null;
  return (
    <div className="page">
      <Button className="back-button" type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/drafts")}>
        返回草稿列表
      </Button>
      <PageHeader
        eyebrow={`版本 v${draft.current_version}`}
        title="草稿审核"
        description={draft.question_title}
        actions={
          <Space>
            <span className={dirty ? "save-status save-status--dirty" : "save-status"}>
              {dirty ? "有未保存修改" : <><CheckOutlined /> 已保存</>}
            </span>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              disabled={!dirty || !title.trim() || !content.trim()}
              loading={mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              保存新版本
            </Button>
          </Space>
        }
      />
      <Alert
        className="phase-alert"
        type="warning"
        showIcon
        title="第一阶段最小草稿"
        description="这不是第二阶段的正式总结文章。它只用于验证结构化分析、版本保存和人工审核入口。"
      />
      <div className="draft-review-grid">
        <section className="work-surface draft-editor">
          <div className="section-heading">
            <h2>文章编辑器</h2>
            <StatusTag status={draft.status} />
          </div>
          <label htmlFor="draft-title">草稿标题</label>
          <Input
            id="draft-title"
            value={title}
            maxLength={500}
            onChange={(event) => {
              setTitle(event.target.value);
              setDirty(true);
            }}
          />
          <label htmlFor="draft-content">Markdown 正文</label>
          <Input.TextArea
            id="draft-content"
            className="draft-textarea"
            value={content}
            onChange={(event) => {
              setContent(event.target.value);
              setDirty(true);
            }}
          />
        </section>
        <section className="work-surface draft-preview-panel">
          <div className="section-heading">
            <h2>实时预览</h2>
            <Button type="link" icon={<LinkOutlined />} onClick={() => navigate(`/questions/${draft.question_id}`)}>
              查看来源问题
            </Button>
          </div>
          <MarkdownPreview content={content} />
        </section>
        <aside className="work-surface draft-source-panel">
          <h2>来源与质量提示</h2>
          <dl className="source-facts">
            <div><dt>来源问题</dt><dd>{draft.question_title}</dd></div>
            <div><dt>观点数量</dt><dd>{draft.analysis_snapshot.core_claims?.length ?? 0}</dd></div>
            <div><dt>质量分</dt><dd>{draft.analysis_snapshot.quality_score ?? "—"}</dd></div>
            <div><dt>相关性</dt><dd>{draft.analysis_snapshot.relevance_score ?? "—"}</dd></div>
          </dl>
          <Alert
            type="info"
            showIcon
            title="人工审核必需"
            description="真实回答来源映射、聚类和独立质量审核将在第二阶段完成。当前草稿不能进入正式发布。"
          />
        </aside>
      </div>
    </div>
  );
}
