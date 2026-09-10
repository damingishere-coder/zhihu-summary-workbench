import {
  ArrowLeftOutlined,
  BoldOutlined,
  CheckOutlined,
  CloseOutlined,
  FormOutlined,
  ReloadOutlined,
  SaveOutlined,
  SafetyCertificateOutlined,
  ScissorOutlined,
  UndoOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Collapse,
  Input,
  Drawer,
  Progress,
  Space,
  Tabs,
  Tag,
  Tooltip,
} from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { UnsavedChangesGuard } from "../components/UnsavedChangesGuard";
import { ExportReadiness } from "../components/ExportReadiness";
import { ImagePromptWorkspace } from "../components/ImagePromptWorkspace";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import type { ParagraphSource } from "../types";
import { formatDateTime } from "../utils/format";

const stanceNames: Record<string, string> = { supports: "支持", conditional: "有条件认同", opposes: "反对", mixed: "混合态度", related: "仅相关提及" };

function MarkdownPreview({ content }: { content: string }) {
  return (
    <article className="markdown-preview">
      {content.split(/\r?\n/).map((line, index) => {
        if (line.startsWith("# ")) return <h1 key={index}>{line.slice(2)}</h1>;
        if (line.startsWith("## ")) return <h2 key={index}>{line.slice(3)}</h2>;
        if (line.startsWith("- ")) return <li key={index}>{line.slice(2)}</li>;
        if (line.startsWith("> "))
          return <blockquote key={index}>{line.slice(2)}</blockquote>;
        return line ? <p key={index}>{line}</p> : <br key={index} />;
      })}
    </article>
  );
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function markdownToSafeHtml(content: string) {
  const lines = content.split(/\r?\n/);
  const html: string[] = [];
  let listOpen = false;
  const closeList = () => {
    if (listOpen) {
      html.push("</ul>");
      listOpen = false;
    }
  };
  lines.forEach((line) => {
    if (line.startsWith("- ")) {
      if (!listOpen) {
        html.push("<ul>");
        listOpen = true;
      }
      html.push(`<li>${escapeHtml(line.slice(2))}</li>`);
      return;
    }
    closeList();
    if (line.startsWith("# "))
      html.push(`<h1>${escapeHtml(line.slice(2))}</h1>`);
    else if (line.startsWith("## "))
      html.push(`<h2>${escapeHtml(line.slice(3))}</h2>`);
    else if (line.startsWith("> "))
      html.push(`<blockquote>${escapeHtml(line.slice(2))}</blockquote>`);
    else if (line) html.push(`<p>${escapeHtml(line)}</p>`);
    else html.push("<p><br></p>");
  });
  closeList();
  return html.join("");
}

function richTextToMarkdown(root: HTMLElement) {
  const blocks = Array.from(root.children).flatMap((element) => {
    const text = (element.textContent ?? "").trim();
    if (element.tagName === "H1") return [`# ${text}`];
    if (element.tagName === "H2") return [`## ${text}`];
    if (element.tagName === "BLOCKQUOTE") return [`> ${text}`];
    if (element.tagName === "UL" || element.tagName === "OL") {
      return Array.from(element.children).map(
        (item) => `- ${(item.textContent ?? "").trim()}`,
      );
    }
    return [text];
  });
  return blocks
    .join("\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function replaceTextRange(
  content: string,
  start: number,
  end: number,
  replacement: string,
) {
  return `${content.slice(0, start)}${replacement}${content.slice(end)}`;
}

export function paragraphRange(content: string, cursor: number) {
  const safeCursor = Math.max(0, Math.min(cursor, content.length));
  const previousBreak = content.lastIndexOf("\n\n", safeCursor - 1);
  const nextBreak = content.indexOf("\n\n", safeCursor);
  return {
    start: previousBreak < 0 ? 0 : previousBreak + 2,
    end: nextBreak < 0 ? content.length : nextBreak,
  };
}

function RichTextEditor({
  value,
  onChange,
  onFocus,
  onBlur,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onFocus: () => void;
  onBlur: () => void;
  disabled?: boolean;
}) {
  const editorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (editorRef.current && document.activeElement !== editorRef.current) {
      editorRef.current.innerHTML = markdownToSafeHtml(value);
    }
  }, [value]);
  const syncValue = () => {
    if (editorRef.current) onChange(richTextToMarkdown(editorRef.current));
  };
  const format = (command: string, argument?: string) => {
    editorRef.current?.focus();
    document.execCommand(command, false, argument);
    syncValue();
  };
  return (
    <div className="rich-text-editor">
      <div className="rich-text-toolbar">
        <Tooltip title="二级标题">
          <Button size="small" onClick={() => format("formatBlock", "h2")}>
            H2
          </Button>
        </Tooltip>
        <Tooltip title="加粗">
          <Button
            size="small"
            icon={<BoldOutlined />}
            onClick={() => format("bold")}
          />
        </Tooltip>
        <Tooltip title="项目符号">
          <Button
            size="small"
            icon={<UnorderedListOutlined />}
            onClick={() => format("insertUnorderedList")}
          />
        </Tooltip>
      </div>
      <div
        ref={editorRef}
        className="rich-text-surface"
        contentEditable={!disabled}
        role="textbox"
        aria-label="富文本草稿编辑器"
        suppressContentEditableWarning
        onInput={syncValue}
        onFocus={onFocus}
        onBlur={onBlur}
      />
    </div>
  );
}

const checkLabels: Record<string, string> = {
  covers_consensus: "覆盖主流共识",
  covers_disagreement: "覆盖主要分歧",
  sources_traceable: "段落来源可追溯",
  ai_notice_present: "包含 AI 辅助说明",
  no_absolute_claims: "没有绝对化表达",
};

export function groupParagraphSources(sources: ParagraphSource[]) {
  return sources.reduce<Record<string, ParagraphSource[]>>((groups, source) => {
    (groups[source.paragraph_id] ??= []).push(source);
    return groups;
  }, {});
}

export function DraftReviewPage() {
  const { id } = useParams();
  return <DraftWorkspace key={id} />;
}

function DraftWorkspace() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { message, modal } = App.useApp();
  const [params, setParams] = useSearchParams();
  const step = ["article", "image", "review"].includes(params.get("step") ?? "")
    ? params.get("step")!
    : "article";
  const changeStep = (next: string) =>
    setParams(
      (previous) => {
        const values = new URLSearchParams(previous);
        values.set("step", next);
        return values;
      },
      { replace: true, preventScrollReset: true },
    );
  const [editorMode, setEditorMode] = useState("preview");
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [imageDirty, setImageDirty] = useState(false);
  const [imageBusy, setImageBusy] = useState(false);
  const returnTo = params.get("returnTo");
  const backTo =
    returnTo === "/drafts" ||
    returnTo?.startsWith("/drafts?") ||
    returnTo === "/publish" ||
    returnTo?.startsWith("/publish?")
      ? returnTo
      : "/drafts";
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["drafts", id],
    queryFn: () => api.draft(id),
    enabled: Boolean(id),
  });
  const versionsQuery = useQuery({
    queryKey: ["draft-versions", id],
    queryFn: () => api.draftVersions(id),
    enabled: Boolean(id),
  });
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const [undoStack, setUndoStack] = useState<string[]>([]);
  const [rewriteInstruction, setRewriteInstruction] = useState("");
  const [selection, setSelection] = useState({ start: 0, end: 0 });
  const editBaselineRef = useRef<string | null>(null);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    if (query.data && !dirtyRef.current) {
      setTitle(query.data.title);
      setContent(query.data.content);
      setDirty(false);
      setUndoStack([]);
      editBaselineRef.current = null;
    }
  }, [query.data]);
  const beginEdit = () => {
    if (editBaselineRef.current === null) editBaselineRef.current = content;
  };
  const finishEdit = () => {
    const baseline = editBaselineRef.current;
    if (baseline !== null && baseline !== content) {
      setUndoStack((values) => [...values, baseline].slice(-30));
    }
    editBaselineRef.current = null;
  };
  const changeContent = (value: string) => {
    setContent(value);
    setDirty(true);
  };
  const undoContent = () => {
    const previous = undoStack.at(-1);
    if (previous === undefined) return;
    setUndoStack((values) => values.slice(0, -1));
    setContent(previous);
    setDirty(true);
  };
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["drafts"] }),
      queryClient.invalidateQueries({ queryKey: ["draft-versions", id] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["publish-readiness", id] }),
      queryClient.invalidateQueries({
        queryKey: ["drafts", "publish-readiness"],
      }),
    ]);
  };
  const saveMutation = useMutation({
    mutationFn: () => api.updateDraft(id, { title, content }),
    onSuccess: async (draft) => {
      message.success(`已保存为版本 v${draft.current_version}，需要重新审核`);
      queryClient.setQueryData(["drafts", id], draft);
      setTitle(draft.title);
      setContent(draft.content);
      dirtyRef.current = false;
      setDirty(false);
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const reviewMutation = useMutation({
    mutationFn: () => api.reviewDraft(id),
    onSuccess: async () => {
      message.success("独立质量审核已更新");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const approvalMutation = useMutation({
    mutationFn: (action: "approve" | "reject") =>
      action === "approve" ? api.approveDraft(id) : api.rejectDraft(id),
    onSuccess: async (draft) => {
      message.success(
        draft.status === "review_approved"
          ? "草稿已通过人工审核"
          : "草稿已退回分析",
      );
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const regenerateMutation = useMutation({
    mutationFn: () => api.regenerateDraft(id),
    onSuccess: async () => {
      message.success("文章和独立审核已重新生成");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const rewriteMutation = useMutation({
    mutationFn: (payload: {
      scope: "paragraph" | "selection";
      start: number;
      end: number;
      text: string;
      baseContent: string;
    }) =>
      api.rewriteDraftText(id, {
        scope: payload.scope,
        text: payload.text,
        instruction: rewriteInstruction,
      }),
    onSuccess: (result, payload) => {
      setUndoStack((values) => [...values, payload.baseContent].slice(-30));
      setContent(
        replaceTextRange(
          payload.baseContent,
          payload.start,
          payload.end,
          result.text,
        ),
      );
      setSelection({
        start: payload.start,
        end: payload.start + result.text.length,
      });
      setDirty(true);
      message.success(
        payload.scope === "selection" ? "选中文字已重写" : "当前段落已重写",
      );
    },
    onError: (error) => message.error(error.message),
  });
  const rewrite = (scope: "paragraph" | "selection") => {
    const range =
      scope === "selection" && selection.end > selection.start
        ? selection
        : paragraphRange(content, selection.start);
    const text = content.slice(range.start, range.end).trim();
    if (!text) {
      message.warning("请先把光标放到要重写的段落，或选中一段文字");
      return;
    }
    rewriteMutation.mutate({
      scope,
      start: range.start,
      end: range.end,
      text,
      baseContent: content,
    });
  };

  const groupedSources = useMemo(
    () => groupParagraphSources(query.data?.paragraph_sources ?? []),
    [query.data?.paragraph_sources],
  );

  const busy =
    saveMutation.isPending ||
    reviewMutation.isPending ||
    approvalMutation.isPending ||
    regenerateMutation.isPending ||
    rewriteMutation.isPending;

  if (query.isLoading)
    return (
      <div className="page">
        <LoadingBlock rows={18} />
      </div>
    );
  if (query.isError) {
    return (
      <div className="page">
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </div>
    );
  }
  const draft = query.data;
  if (!draft) return null;
  const review = draft.review_result;
  const hasReview = typeof review.score === "number";
  const approvalActions = (
    <div className="draft-review-actions">
      <Button
        danger
        icon={<CloseOutlined />}
        disabled={dirty || imageDirty || busy || imageBusy}
        loading={approvalMutation.isPending}
        onClick={() => approvalMutation.mutate("reject")}
      >
        退回分析
      </Button>
      <Button
        type="primary"
        icon={<CheckOutlined />}
        disabled={
          !hasReview ||
          dirty ||
          imageDirty ||
          busy ||
          imageBusy ||
          draft.status === "review_approved"
        }
        loading={approvalMutation.isPending}
        onClick={() => approvalMutation.mutate("approve")}
      >
        人工审核通过
      </Button>
    </div>
  );

  return (
    <div className="page work-editor-page">
      <UnsavedChangesGuard
        dirty={dirty || imageDirty}
        busy={busy || imageBusy}
        onSave={
          dirty && !imageDirty && title.trim() && content.trim()
            ? () => saveMutation.mutateAsync()
            : undefined
        }
      />
      <Button
        className="back-button"
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate(backTo)}
      >
        返回作品列表
      </Button>
      <PageHeader
        eyebrow={`文章版本 v${draft.current_version}`}
        title={draft.title}
        description={`来自选题：${draft.question_title}`}
        actions={
          <Space wrap>
            <span
              className={
                dirty ? "save-status save-status--dirty" : "save-status"
              }
            >
              {dirty ? (
                "有未保存修改"
              ) : (
                <>
                  <CheckOutlined /> 已保存
                </>
              )}
            </span>
            <Button
              icon={<ReloadOutlined />}
              disabled={dirty || imageDirty || busy || imageBusy}
              loading={regenerateMutation.isPending}
              onClick={() => regenerateMutation.mutate()}
            >
              重新生成文章
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              disabled={
                !dirty || !title.trim() || !content.trim() || busy || imageBusy
              }
              loading={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              保存新版本
            </Button>
          </Space>
        }
      />
      <nav className="work-steps" aria-label="作品检查步骤">
        {[
          ["article", "文章"],
          ["image", "配图"],
          ["review", "审核与导出"],
        ].map(([key, label], index) => (
          <button
            key={key}
            aria-current={step === key ? "step" : undefined}
            onClick={() => changeStep(key)}
          >
            <span>{index + 1}</span>
            {label}
          </button>
        ))}
      </nav>
      {review.risk_level === "high" && (
        <Alert
          className="phase-alert"
          type="error"
          showIcon
          title="高风险内容必须人工审核"
          description="当前问题涉及医疗、法律、金融或投资风险；请逐段核验原回答和事实后再通过。"
        />
      )}

      <div className="work-editor-body">
        <section
          className="work-surface draft-editor"
          hidden={step !== "article"}
        >
          <div className="section-heading">
            <div>
              <h2>文章</h2>
              <p>高度归纳，500字以内 · 当前 {Array.from((title + content).replace(/\s/g, "")).length}/500 字</p>
            </div>
            <Space wrap>
              <Button onClick={() => setSourcesOpen(true)}>来源与完整统计</Button>
              <Button onClick={() => setEditorMode("versions")}>
                历史版本
              </Button>
              <Button
                onClick={() =>
                  setEditorMode(editorMode === "preview" ? "edit" : "preview")
                }
              >
                {editorMode === "preview" ? "编辑文章" : "阅读预览"}
              </Button>
              <StatusTag status={draft.status} />
            </Space>
          </div>
          <fieldset
            className="editor-fields"
            disabled={busy || imageBusy}
            inert={busy || imageBusy}
          >
            <div hidden={editorMode === "preview" || editorMode === "versions"}>
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
              <div className="draft-rewrite-toolbar">
                <Input
                  value={rewriteInstruction}
                  allowClear
                  placeholder="重写要求（可选），例如：更简洁、保留条件和风险"
                  onChange={(event) =>
                    setRewriteInstruction(event.target.value)
                  }
                />
                <Space wrap>
                  <Button
                    size="small"
                    icon={<ScissorOutlined />}
                    disabled={selection.end <= selection.start}
                    loading={rewriteMutation.isPending}
                    onClick={() => rewrite("selection")}
                  >
                    重写选中文字
                  </Button>
                  <Button
                    size="small"
                    icon={<FormOutlined />}
                    loading={rewriteMutation.isPending}
                    onClick={() => rewrite("paragraph")}
                  >
                    重写当前段落
                  </Button>
                  <Button
                    size="small"
                    icon={<UndoOutlined />}
                    disabled={undoStack.length === 0}
                    onClick={undoContent}
                  >
                    撤销
                  </Button>
                </Space>
              </div>
            </div>
            <Tabs
              activeKey={editorMode}
              onChange={setEditorMode}
              className={`draft-editor-tabs ${editorMode === "preview" ? "draft-editor-tabs--reading" : ""}`}
              items={[
                {
                  key: "edit",
                  label: "Markdown 编辑",
                  children: (
                    <Input.TextArea
                      id="draft-content"
                      aria-label="文章正文"
                      className="draft-textarea"
                      value={content}
                      onFocus={beginEdit}
                      onBlur={finishEdit}
                      onSelect={(event) => {
                        const target = event.currentTarget;
                        setSelection({
                          start: target.selectionStart,
                          end: target.selectionEnd,
                        });
                      }}
                      onChange={(event) => changeContent(event.target.value)}
                    />
                  ),
                },
                {
                  key: "rich",
                  label: "富文本编辑",
                  children: (
                    <RichTextEditor
                      value={content}
                      disabled={busy || imageBusy}
                      onChange={changeContent}
                      onFocus={beginEdit}
                      onBlur={finishEdit}
                    />
                  ),
                },
                {
                  key: "preview",
                  label: "阅读预览",
                  children: <MarkdownPreview content={content} />,
                },
                {
                  key: "versions",
                  label: `历史版本 ${versionsQuery.data?.length ?? 0}`,
                  children: (
                    <div className="draft-version-list">
                      {versionsQuery.data?.map((version) => (
                        <div key={version.id}>
                          <div>
                            <strong>v{version.version}</strong>
                            <span>
                              {formatDateTime(version.created_at, true)}
                            </span>
                            <small>{version.title}</small>
                          </div>
                          <Button
                            size="small"
                            disabled={busy}
                            onClick={() => {
                              const restore = () => {
                                setUndoStack((values) =>
                                  [...values, content].slice(-30),
                                );
                                setTitle(version.title);
                                setContent(version.content);
                                setDirty(true);
                                setEditorMode("edit");
                              };
                              if (dirty)
                                modal.confirm({
                                  title: "用历史版本替换未保存修改？",
                                  content:
                                    "当前未保存的标题和正文会被替换，恢复后仍需保存。",
                                  okText: "替换到编辑器",
                                  cancelText: "保留修改",
                                  onOk: restore,
                                });
                              else restore();
                            }}
                          >
                            恢复到编辑器
                          </Button>
                        </div>
                      ))}
                    </div>
                  ),
                },
              ]}
            />
          </fieldset>
        </section>

        <section
          className="work-surface draft-image-column"
          hidden={step !== "image"}
        >
          <ImagePromptWorkspace
            draftId={draft.id}
            onDirtyChange={setImageDirty}
            onBusyChange={setImageBusy}
          />
        </section>

        <aside
          className="work-surface draft-source-panel"
          hidden={step !== "review"}
        >
          <div className="section-heading">
            <div>
              <h2>审核与导出</h2>
              <p>核对依据与图文，确认后再导出。</p>
            </div>
            {hasReview && (
              <Tag color={review.passed ? "success" : "warning"}>
                {review.passed ? "独立审核通过" : "独立审核未通过"} ·{" "}
                {review.score} 分
              </Tag>
            )}
          </div>
          {hasReview ? (
            <>
              <Progress
                percent={review.score}
                status={review.passed ? "success" : "exception"}
                strokeColor={review.passed ? undefined : "var(--wb-warning)"}
              />
              <div className="quality-check-list">
                {Object.entries(review.checks ?? {}).map(([key, passed]) => (
                  <div key={key}>
                    {passed ? <CheckOutlined /> : <CloseOutlined />}
                    <span>{checkLabels[key] ?? key}</span>
                  </div>
                ))}
              </div>
              {(review.issues ?? []).length > 0 && (
                <Collapse
                  items={[
                    {
                      key: "issues",
                      label: `完整审核意见 · ${(review.issues ?? []).length} 条`,
                      children: (
                        <ul>
                          {(review.issues ?? []).map((issue) => (
                            <li key={issue}>{issue}</li>
                          ))}
                        </ul>
                      ),
                    },
                  ]}
                />
              )}
              <p className="quality-summary">{review.summary}</p>
            </>
          ) : (
            <Alert type="warning" showIcon title="尚未完成独立质量审核" />
          )}
          <Button
            block
            icon={<SafetyCertificateOutlined />}
            disabled={dirty || imageDirty || busy || imageBusy}
            loading={reviewMutation.isPending}
            onClick={() => reviewMutation.mutate()}
          >
            重新运行独立审核
          </Button>

          <div className="coverage-summary">
            <h3>来源与采集范围</h3>
            <p>
              {draft.analysis_snapshot.opinion_survey ? `保存 ${draft.analysis_snapshot.opinion_survey.collected_answers} 条回答，分析 ${draft.analysis_snapshot.opinion_survey.analyzed_answers} 条。${draft.analysis_snapshot.capture?.stop_reason === "no_progress" ? "连续三轮无新增后停止，未确认覆盖全部回答。" : "仅代表已采集样本。"}` : draft.content
                .split("\n")
                .find((line) => line.includes("采集范围："))
                ?.replace(/^>\s*/, "") ||
                `当前版本记录 ${draft.analysis_snapshot.answer_count ?? "未知数量的"} 条来源回答；未记录完整覆盖信息，不能视为读取全部回答。`}
            </p>
            <Button onClick={() => setSourcesOpen(true)}>逐段查看来源</Button>
          </div>

          {step === "review" && (
            <ExportReadiness
              draftId={draft.id}
              blocked={dirty || imageDirty || busy || imageBusy}
            />
          )}
        </aside>
      </div>
      <footer className="work-step-footer">
        <Button
          disabled={step === "article"}
          onClick={() => changeStep(step === "review" ? "image" : "article")}
        >
          上一步
        </Button>
        <span>{dirty || imageDirty ? "有未保存修改" : "可以随时返回检查"}</span>
        {step === "review" && approvalActions}
        {step !== "review" && (
          <Button
            type="primary"
            onClick={() => changeStep(step === "article" ? "image" : "review")}
          >
            {step === "article" ? "下一步：检查配图" : "下一步：审核与导出"}
          </Button>
        )}
      </footer>
      <Drawer
        title="来源与完整统计"
        size="min(560px, 94vw)"
        open={sourcesOpen}
        onClose={() => setSourcesOpen(false)}
      >
        {draft.analysis_snapshot.opinion_survey && (
          <details style={{ marginBottom: 24 }}>
            <summary>完整观点统计（{draft.analysis_snapshot.opinion_survey.rows.length} 项）</summary>
            <p>保存 {draft.analysis_snapshot.opinion_survey.collected_answers} 条，分析 {draft.analysis_snapshot.opinion_survey.analyzed_answers} 条；分母 {draft.analysis_snapshot.opinion_survey.denominator} 位作者。未判定态度 {draft.analysis_snapshot.opinion_survey.unclassified_authors} 位。</p>
            <p>{draft.analysis_snapshot.opinion_survey.method}</p>
            {draft.analysis_snapshot.capture?.stop_reason === "no_progress" && <p>采集停止原因：连续三轮回滑无新增；保留当时可访问的回答，未确认覆盖全部回答。</p>}
            {draft.analysis_snapshot.opinion_survey.rows.map(row => (
              <details key={row.cluster_id} style={{ padding: "10px 0", borderBottom: "1px solid var(--border-color, #ddd)" }}>
                <summary>{row.name} · 认同 {row.endorsement_count} 人（{row.endorsement_percent ?? "未知"}%）</summary>
                <p>反对 {row.counts.opposes} · 混合 {row.counts.mixed} · 仅相关提及 {row.counts.related}</p>
                {row.evidence.map(e => <p key={e.answer_id}><a href={e.answer_url} target="_blank" rel="noreferrer">{e.author_name}</a> · {stanceNames[e.relation] ?? e.relation}<br />{e.quote}</p>)}
              </details>
            ))}
          </details>
        )}
        <h3>段落来源</h3>
        {Object.keys(groupedSources).length ? (
          <Collapse
            ghost
            className="paragraph-source-list"
            items={Object.entries(groupedSources).map(
              ([paragraphId, sources]) => ({
                key: paragraphId,
                label: `${paragraphId} · ${sources.filter((item) => item.answer_id).length} 条回答来源`,
                children: (
                  <div>
                    {sources.map((source, index) => (
                      <div
                        className="paragraph-source-item"
                        key={`${paragraphId}-${index}`}
                      >
                        {source.answer_id ? (
                          <>
                            <a
                              href={source.answer_url ?? "#"}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {source.answer_author || "原回答"}
                            </a>
                            <p>{source.answer_excerpt}</p>
                          </>
                        ) : source.cluster_name ? (
                          <Tag>{source.cluster_name}</Tag>
                        ) : (
                          <span>说明段，无外部来源</span>
                        )}
                      </div>
                    ))}
                  </div>
                ),
              }),
            )}
          />
        ) : (
          <p className="section-empty">当前文章版本没有来源映射。</p>
        )}
      </Drawer>
    </div>
  );
}
