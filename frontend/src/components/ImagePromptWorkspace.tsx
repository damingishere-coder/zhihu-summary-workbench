import {
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  HistoryOutlined,
  HolderOutlined,
  PictureOutlined,
  ReloadOutlined,
  SaveOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Drawer,
  Empty,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Slider,
  Space,
  Switch,
  Tabs,
  Tag,
  Upload,
} from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { InfographicContent } from "../types";
import { formatDateTime } from "../utils/format";

export async function copyPromptText(text: string) {
  let clipboardError: unknown;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {
      clipboardError = error;
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) throw clipboardError ?? new Error("浏览器不支持复制");
}

const emptyContent: InfographicContent = {
  title: "",
  one_line_conclusion: "",
  consensus: [],
  disagreements: [],
  conditions: [],
  suggestions: [],
  visual_keywords: [],
  source_cluster_ids: [],
  source_answer_ids: [],
};

function StringListEditor({
  title,
  values,
  onChange,
}: {
  title: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const move = (from: number, to: number) => {
    const next = [...values];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };
  return (
    <div className="info-list-editor">
      <div className="info-list-editor__heading">
        <strong>{title}</strong>
        <span>{values.length}/4</span>
      </div>
      {values.map((value, index) => (
        <div
          className="info-list-editor__row"
          key={`${title}-${index}`}
          draggable
          onDragStart={(event) => event.dataTransfer.setData("text/index", String(index))}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => move(Number(event.dataTransfer.getData("text/index")), index)}
        >
          <HolderOutlined aria-label="拖动排序" />
          <Input
            value={value}
            maxLength={96}
            showCount
            onChange={(event) =>
              onChange(values.map((item, itemIndex) => itemIndex === index ? event.target.value : item))
            }
          />
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            aria-label={`删除${title}${index + 1}`}
            onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}
          />
        </div>
      ))}
      <Button
        size="small"
        disabled={values.length >= 4}
        onClick={() => onChange([...values, "新增要点"])}
      >
        添加{title}
      </Button>
    </div>
  );
}

function InfographicPreview({
  content,
  template,
  fontScale,
  brand,
  footer,
  backgroundUrl,
  cssMode,
  survey = false,
  renderedUrl,
}: {
  content: InfographicContent;
  template: "knowledge_card" | "comparison_table";
  fontScale: number;
  brand: string;
  footer: string;
  backgroundUrl: string | null;
  cssMode: boolean;
  survey?: boolean;
  renderedUrl?: string | null;
}) {
  if (survey) {
    return renderedUrl ? (
      <figure style={{ margin: 0 }} aria-label="观点统计图预览">
        <img src={renderedUrl} alt="按回答作者统计的观点分布图"
          style={{ display: "block", width: "100%", height: "auto", borderRadius: 12 }} />
        <figcaption>当前文章版本的统计图，预览与下载 PNG 一致。</figcaption>
      </figure>
    ) : <p role="status">观点统计图尚未渲染，完成后在这里显示。</p>;
  }
  return (
    <div
      className={`infographic-preview infographic-preview--${template}`}
      style={{
        fontSize: `${fontScale}em`,
        backgroundImage: !cssMode && backgroundUrl ? `url(${backgroundUrl})` : undefined,
      }}
      aria-label="信息图实时预览"
    >
      <div className="infographic-preview__veil">
        <header>
          <small>{brand}</small>
          <h2>{content.title || "信息图标题"}</h2>
          <p>{content.one_line_conclusion || "一句话结论"}</p>
        </header>
        <div className="infographic-preview__columns">
          <section>
            <strong>{template === "comparison_table" ? "共同判断" : "大家较一致的判断"}</strong>
            {content.consensus.map((item, index) => (
              <article key={`${item.title}-${index}`}>
                <b>{item.title}</b>
                <span>{item.description}</span>
              </article>
            ))}
          </section>
          {template === "comparison_table" && (
            <section>
              <strong>主要分歧</strong>
              {content.disagreements.map((item) => <article key={item}>{item}</article>)}
            </section>
          )}
        </div>
        {template === "knowledge_card" && (
          <div className="infographic-preview__details">
            {[["主要分歧", content.disagreements], ["适用条件", content.conditions], ["行动建议", content.suggestions]].map(
              ([title, values]) => (
                <section key={title as string}>
                  <strong>{title}</strong>
                  <ul>{(values as string[]).map((item) => <li key={item}>{item}</li>)}</ul>
                </section>
              ),
            )}
          </div>
        )}
        <footer><span>{footer}</span><span>来源观点簇 {content.source_cluster_ids.length} 个</span></footer>
      </div>
    </div>
  );
}

export function ImagePromptWorkspace({
  draftId,
  onDirtyChange,
  onBusyChange,
}: {
  draftId: string;
  onDirtyChange?: (dirty: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState("克制的知识编辑插画");
  const [template, setTemplate] = useState<
    "knowledge_card" | "comparison_table"
  >("knowledge_card");
  const [canvasSize, setCanvasSize] = useState<"1080x1440" | "1242x1660">(
    "1080x1440",
  );
  const [fontScale, setFontScale] = useState(1);
  const [brand, setBrand] = useState("知乎问题总结工作台");
  const [footer, setFooter] = useState(
    "内容由 AI 辅助整理，请结合来源人工核验",
  );
  const [backgroundX, setBackgroundX] = useState(50);
  const [backgroundY, setBackgroundY] = useState(50);
  const [backgroundScale, setBackgroundScale] = useState(1);
  const [content, setContent] = useState<InfographicContent>(emptyContent);
  const [baseline, setBaseline] = useState<string | null>(null);
  const signature = JSON.stringify({
    content,
    template,
    canvasSize,
    fontScale,
    brand,
    footer,
    backgroundX,
    backgroundY,
    backgroundScale,
  });
  const dirty = baseline !== null && signature !== baseline;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  const query = useQuery({
    queryKey: ["image-workspace", draftId],
    queryFn: () => api.imageWorkspace(draftId),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({
      queryKey: ["image-workspace", draftId],
    });
    await queryClient.invalidateQueries({
      queryKey: ["publish-readiness", draftId],
    });
    await queryClient.invalidateQueries({
      queryKey: ["drafts", "publish-readiness"],
    });
  };
  const workspace = query.data;
  const current = workspace?.current;
  useEffect(() => {
    if (!current || dirtyRef.current) return;
    const value = current.content_json;
    const nextContent = {
      title: value.title ?? "",
      one_line_conclusion: value.one_line_conclusion ?? "",
      consensus: value.consensus ?? [],
      disagreements: value.disagreements ?? [],
      conditions: value.conditions ?? [],
      suggestions: value.suggestions ?? [],
      visual_keywords: value.visual_keywords ?? [],
      source_cluster_ids: value.source_cluster_ids ?? [],
      source_answer_ids: value.source_answer_ids ?? [],
    };
    setContent(nextContent);
    setBaseline(
      JSON.stringify({
        content: nextContent,
        template: value.template_type ?? "knowledge_card",
        canvasSize: value.canvas_size ?? "1080x1440",
        fontScale: value.font_scale ?? 1,
        brand: value.brand_name ?? "知乎问题总结工作台",
        footer: value.footer_text ?? "内容由 AI 辅助整理，请结合来源人工核验",
        backgroundX: value.background_position_x ?? 50,
        backgroundY: value.background_position_y ?? 50,
        backgroundScale: value.background_scale ?? 1,
      }),
    );
    setTemplate(value.template_type ?? "knowledge_card");
    setCanvasSize(value.canvas_size ?? "1080x1440");
    setFontScale(value.font_scale ?? 1);
    setBrand(value.brand_name ?? "知乎问题总结工作台");
    setFooter(value.footer_text ?? "内容由 AI 辅助整理，请结合来源人工核验");
    setBackgroundX(value.background_position_x ?? 50);
    setBackgroundY(value.background_position_y ?? 50);
    setBackgroundScale(value.background_scale ?? 1);
  }, [current?.id]);

  const generateContent = useMutation({
    mutationFn: () =>
      api.generateInfographicContent(draftId, {
        template_type: template,
        canvas_size: canvasSize,
      }),
    onSuccess: async () => {
      message.success("信息图文案已生成并保存为新版本");
      setOpen(true);
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const save = useMutation({
    mutationFn: () => {
      if (!workspace) throw new Error("请先生成信息图文案");
      return api.updateInfographic(workspace.id, {
        content,
        template_type: template,
        canvas_size: canvasSize,
        font_scale: fontScale,
        brand_name: brand,
        footer_text: footer,
        background_position_x: backgroundX,
        background_position_y: backgroundY,
        background_scale: backgroundScale,
      });
    },
    onSuccess: async () => {
      dirtyRef.current = false;
      setBaseline(signature);
      message.success("编辑内容已保存为新版本");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const generatePrompt = useMutation({
    mutationFn: () =>
      api.generateImagePrompt(draftId, {
        visual_style: style,
        aspect_ratio: "3:4",
      }),
    onSuccess: async () => {
      message.success("图片 Prompt 已生成；请在 ChatGPT 手动生图");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const render = useMutation({
    mutationFn: () => {
      if (!workspace) throw new Error("信息图工作区不存在");
      return api.renderInfographic(workspace.id);
    },
    onSuccess: async (result) => {
      if (result.current?.overflow.length)
        message.warning("检测到文字溢出，请精简内容");
      else message.success("PNG 渲染完成，可下载 1080×1440 成图");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const restore = useMutation({
    mutationFn: (version: number) =>
      api.restoreImageVersion(workspace!.id, version),
    onSuccess: async () => {
      message.success("历史版本已恢复为一个新版本");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const markCopied = useMutation({
    mutationFn: ({ language }: { language: "zh" | "en" }) =>
      api.markImagePromptCopied(workspace!.id, language),
    onSuccess: refresh,
  });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadVisualAsset(draftId, file),
    onSuccess: async () => {
      message.success("背景原图与缩略图已保存为新版本");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const cssMode = useMutation({
    mutationFn: (enabled: boolean) =>
      api.setImageCssMode(workspace!.id, enabled),
    onSuccess: refresh,
    onError: (error) => message.error(error.message),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteImageBackground(workspace!.id),
    onSuccess: async () => {
      message.success("当前背景已移除，历史版本仍保留");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });

  const busy =
    generateContent.isPending ||
    save.isPending ||
    generatePrompt.isPending ||
    render.isPending ||
    restore.isPending ||
    upload.isPending ||
    cssMode.isPending ||
    remove.isPending;
  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  const copy = async (language: "zh" | "en") => {
    if (!current) return;
    try {
      await copyPromptText(
        language === "zh" ? current.prompt_zh : current.prompt_en,
      );
      message.success(
        language === "zh" ? "中文 Prompt 已复制" : "英文 Prompt 已复制",
      );
      markCopied.mutate({ language });
    } catch {
      message.error("浏览器未允许复制，请选中文本后手动复制");
    }
  };
  const contentCount = useMemo(
    () =>
      content.consensus.length +
      content.disagreements.length +
      content.conditions.length +
      content.suggestions.length,
    [content],
  );

  return (
    <section className="image-prompt-workspace">
      <div className="section-heading">
        <div>
          <h2>配图</h2>
          <p>{current?.content_json.opinion_survey ? "核对各观点人数、占比和统计范围。" : "检查成图与文案，也可以替换背景或调整版式。"}</p>
        </div>
        {workspace && <Tag color="blue">v{workspace.current_version}</Tag>}
      </div>
      <p className="image-workflow-note">
        {current?.content_json.opinion_survey ? "图中人数来自当前文章的统计快照；修改观点归类后，需要重新生成文章和统计图。" : "今日计划自动生成配图；需要调整时，可编辑文案、替换背景，再生成 PNG。"}
      </p>
      {query.isLoading && <p role="status">正在读取配图…</p>}
      {query.isError && (
        <Alert
          type="error"
          title={query.error.message}
          action={
            <Button onClick={() => void query.refetch()}>重新加载</Button>
          }
        />
      )}
      {dirty && (
        <Alert
          type="info"
          title="配图有未保存修改，请在编辑器保存后再渲染或切换版本。"
        />
      )}
      <fieldset
        className="editor-fields"
        disabled={busy || query.isLoading || query.isError}
      >
        {!current ? (
          <div className="image-workspace-empty">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="先根据观点地图生成有长度约束的信息图文案"
            />
            <Space wrap>
              <Select
                value={template}
                onChange={setTemplate}
                options={[
                  { value: "knowledge_card", label: "知识总结卡" },
                  { value: "comparison_table", label: "观点对比表" },
                ]}
              />
              <Button
                type="primary"
                icon={<PictureOutlined />}
                loading={generateContent.isPending}
                onClick={() => generateContent.mutate()}
              >
                生成信息图文案
              </Button>
            </Space>
          </div>
        ) : (
          <>
            <InfographicPreview
              content={content}
              template={template}
              fontScale={Math.min(fontScale, 1)}
              brand={brand}
              footer={footer}
              backgroundUrl={current.thumbnail_url ?? current.background_url}
              cssMode={workspace?.use_css_background ?? true}
              survey={Boolean(current.content_json.opinion_survey)}
              renderedUrl={current.rendered_url}
            />
            <div className="image-workspace-summary">
              <span>
                {current.content_json.opinion_survey ? "作者观点统计图" : template === "knowledge_card" ? "知识总结卡" : "观点对比表"}
              </span>
              <span>{contentCount} 个内容点</span>
              <Tag
                color={
                  current.render_status === "rendered" ? "success" : "default"
                }
              >
                {current.render_status === "rendered" ? "已渲染" : "待渲染"}
              </Tag>
            </div>
            <Space wrap>
              <Button
                type="primary"
                icon={<EditOutlined />}
                onClick={() => setOpen(true)}
              >
                打开完整编辑器
              </Button>
              <Button
                icon={<ReloadOutlined />}
                loading={generateContent.isPending}
                onClick={() => generateContent.mutate()}
              >
                重新生成文案
              </Button>
              {current.download_url && (
                <Button icon={<DownloadOutlined />} href={current.download_url}>
                  下载 PNG
                </Button>
              )}
            </Space>
          </>
        )}
      </fieldset>
      <Drawer
        className="infographic-editor-drawer"
        size="min(1180px, 96vw)"
        title={`信息图编辑器 · v${workspace?.current_version ?? 0}`}
        open={open}
        onClose={() => setOpen(false)}
        extra={
          <Space>
            <Button
              icon={<SaveOutlined />}
              loading={save.isPending}
              disabled={!dirty || busy}
              onClick={() => save.mutate()}
            >
              保存新版本
            </Button>
            <Button
              type="primary"
              icon={<PictureOutlined />}
              loading={render.isPending}
              disabled={dirty || busy}
              onClick={() => render.mutate()}
            >
              渲染 PNG
            </Button>
          </Space>
        }
      >
        {current && workspace && (
          <fieldset className="editor-fields" disabled={busy} inert={busy}>
            <div className="infographic-editor-layout">
              <div className="infographic-editor-controls">
                <Tabs
                  items={[
                    {
                      key: "content",
                      label: "内容编辑",
                      children: (
                        <div className="infographic-control-stack">
                          <label>标题（最多 48 字）</label>
                          <Input
                            value={content.title}
                            maxLength={48}
                            showCount
                            onChange={(event) =>
                              setContent({
                                ...content,
                                title: event.target.value,
                              })
                            }
                          />
                          <label>一句话结论（最多 96 字）</label>
                          <Input.TextArea
                            value={content.one_line_conclusion}
                            maxLength={96}
                            showCount
                            autoSize={{ minRows: 2, maxRows: 4 }}
                            onChange={(event) =>
                              setContent({
                                ...content,
                                one_line_conclusion: event.target.value,
                              })
                            }
                          />
                          <div className="info-list-editor">
                            <div className="info-list-editor__heading">
                              <strong>共识</strong>
                              <span>{content.consensus.length}/4</span>
                            </div>
                            {content.consensus.map((item, index) => (
                              <div
                                className="consensus-editor-row"
                                key={`${item.title}-${index}`}
                                draggable
                                onDragStart={(event) =>
                                  event.dataTransfer.setData(
                                    "consensus/index",
                                    String(index),
                                  )
                                }
                                onDragOver={(event) => event.preventDefault()}
                                onDrop={(event) => {
                                  const from = Number(
                                    event.dataTransfer.getData(
                                      "consensus/index",
                                    ),
                                  );
                                  const next = [...content.consensus];
                                  const [moved] = next.splice(from, 1);
                                  next.splice(index, 0, moved);
                                  setContent({ ...content, consensus: next });
                                }}
                              >
                                <HolderOutlined />
                                <div className="consensus-editor-fields">
                                  <Input
                                    value={item.title}
                                    maxLength={28}
                                    placeholder="共识标题"
                                    onChange={(event) =>
                                      setContent({
                                        ...content,
                                        consensus: content.consensus.map(
                                          (value, itemIndex) =>
                                            itemIndex === index
                                              ? {
                                                  ...value,
                                                  title: event.target.value,
                                                }
                                              : value,
                                        ),
                                      })
                                    }
                                  />
                                  <Input.TextArea
                                    value={item.description}
                                    maxLength={110}
                                    showCount
                                    autoSize={{ minRows: 2, maxRows: 3 }}
                                    placeholder="共识说明"
                                    onChange={(event) =>
                                      setContent({
                                        ...content,
                                        consensus: content.consensus.map(
                                          (value, itemIndex) =>
                                            itemIndex === index
                                              ? {
                                                  ...value,
                                                  description:
                                                    event.target.value,
                                                }
                                              : value,
                                        ),
                                      })
                                    }
                                  />
                                </div>
                                <Button
                                  type="text"
                                  danger
                                  icon={<DeleteOutlined />}
                                  onClick={() =>
                                    setContent({
                                      ...content,
                                      consensus: content.consensus.filter(
                                        (_, itemIndex) => itemIndex !== index,
                                      ),
                                    })
                                  }
                                />
                              </div>
                            ))}
                          </div>
                          <StringListEditor
                            title="主要分歧"
                            values={content.disagreements}
                            onChange={(values) =>
                              setContent({ ...content, disagreements: values })
                            }
                          />
                          <StringListEditor
                            title="适用条件"
                            values={content.conditions}
                            onChange={(values) =>
                              setContent({ ...content, conditions: values })
                            }
                          />
                          <StringListEditor
                            title="行动建议"
                            values={content.suggestions}
                            onChange={(values) =>
                              setContent({ ...content, suggestions: values })
                            }
                          />
                        </div>
                      ),
                    },
                    {
                      key: "design",
                      label: "版式与背景",
                      children: (
                        <div className="infographic-control-stack">
                          <label>模板</label>
                          <Select
                            value={template}
                            onChange={setTemplate}
                            options={[
                              { value: "knowledge_card", label: "知识总结卡" },
                              {
                                value: "comparison_table",
                                label: "观点对比表",
                              },
                            ]}
                          />
                          <label>画布尺寸</label>
                          <Select
                            value={canvasSize}
                            onChange={setCanvasSize}
                            options={[
                              {
                                value: "1080x1440",
                                label: "1080 × 1440（推荐）",
                              },
                              { value: "1242x1660", label: "1242 × 1660" },
                            ]}
                          />
                          <label>字号缩放 {fontScale.toFixed(2)}</label>
                          <Slider
                            min={0.8}
                            max={1.25}
                            step={0.05}
                            value={fontScale}
                            onChange={setFontScale}
                          />
                          <label>品牌名</label>
                          <Input
                            value={brand}
                            maxLength={32}
                            onChange={(event) => setBrand(event.target.value)}
                          />
                          <label>页脚说明</label>
                          <Input
                            value={footer}
                            maxLength={64}
                            onChange={(event) => setFooter(event.target.value)}
                          />
                          <div className="background-workflow__heading">
                            <div>
                              <strong>背景来源</strong>
                              <p>未上传时保持纯 CSS，上传失败不阻塞。</p>
                            </div>
                            <Space>
                              <span>纯 CSS</span>
                              <Switch
                                disabled={dirty || busy}
                                checked={workspace.use_css_background}
                                loading={cssMode.isPending}
                                onChange={(enabled) => cssMode.mutate(enabled)}
                              />
                            </Space>
                          </div>
                          <Upload
                            disabled={dirty || busy}
                            accept="image/png,image/jpeg,image/webp"
                            showUploadList={false}
                            customRequest={({ file, onSuccess, onError }) =>
                              upload.mutate(file as File, {
                                onSuccess: () => onSuccess?.({}),
                                onError: (error) => onError?.(error),
                              })
                            }
                          >
                            <Button
                              icon={<UploadOutlined />}
                              disabled={dirty || busy}
                              loading={upload.isPending}
                            >
                              上传或替换手动背景图
                            </Button>
                          </Upload>
                          {current.background_url && (
                            <Popconfirm
                              disabled={dirty || busy}
                              title="移除当前背景图？"
                              description="历史版本与原始文件仍保留。"
                              onConfirm={() => remove.mutate()}
                            >
                              <Button danger icon={<DeleteOutlined />}>
                                移除当前背景
                              </Button>
                            </Popconfirm>
                          )}
                          <label>背景水平位置 {backgroundX}%</label>
                          <Slider
                            min={0}
                            max={100}
                            value={backgroundX}
                            onChange={setBackgroundX}
                          />
                          <label>背景垂直位置 {backgroundY}%</label>
                          <Slider
                            min={0}
                            max={100}
                            value={backgroundY}
                            onChange={setBackgroundY}
                          />
                          <label>背景缩放</label>
                          <InputNumber
                            min={1}
                            max={2}
                            step={0.1}
                            value={backgroundScale}
                            onChange={(value) => setBackgroundScale(value ?? 1)}
                          />
                        </div>
                      ),
                    },
                    {
                      key: "prompt",
                      label: "手动图片 Prompt",
                      children: (
                        <div className="prompt-copy-panel">
                          <Alert
                            type="info"
                            showIcon
                            title="这里只生成 Prompt，不调用图片 API"
                            description="复制到 ChatGPT 手动生图后，在“版式与背景”上传原图。"
                          />
                          <Select
                            value={style}
                            onChange={setStyle}
                            options={[
                              {
                                value: "克制的知识编辑插画",
                                label: "知识编辑插画",
                              },
                              {
                                value: "低干扰的抽象几何拼贴",
                                label: "抽象几何拼贴",
                              },
                              {
                                value: "理性的数据叙事插画",
                                label: "数据叙事插画",
                              },
                            ]}
                          />
                          <Button
                            icon={<ReloadOutlined />}
                            loading={generatePrompt.isPending}
                            disabled={dirty || busy}
                            onClick={() => generatePrompt.mutate()}
                          >
                            生成新 Prompt 版本
                          </Button>
                          <label>中文 Prompt</label>
                          <Input.TextArea
                            readOnly
                            autoSize={{ minRows: 8, maxRows: 14 }}
                            value={current.prompt_zh}
                          />
                          <Button
                            icon={<CopyOutlined />}
                            disabled={!current.prompt_zh}
                            onClick={() => void copy("zh")}
                          >
                            复制中文 Prompt
                          </Button>
                          <label>英文 Prompt</label>
                          <Input.TextArea
                            readOnly
                            autoSize={{ minRows: 8, maxRows: 14 }}
                            value={current.prompt_en}
                          />
                          <Button
                            icon={<CopyOutlined />}
                            disabled={!current.prompt_en}
                            onClick={() => void copy("en")}
                          >
                            复制英文 Prompt
                          </Button>
                        </div>
                      ),
                    },
                    {
                      key: "history",
                      label: (
                        <>
                          <HistoryOutlined /> 历史 {workspace.versions.length}
                        </>
                      ),
                      children: (
                        <div className="image-version-list image-version-list--actions">
                          {workspace.versions.map((version) => (
                            <div key={version.id}>
                              <strong>v{version.version}</strong>
                              <span>
                                {formatDateTime(version.created_at, true)}
                              </span>
                              <Tag
                                color={
                                  version.render_status === "rendered"
                                    ? "success"
                                    : "default"
                                }
                              >
                                {version.render_status}
                              </Tag>
                              <Button
                                size="small"
                                loading={restore.isPending}
                                disabled={dirty || busy}
                                onClick={() => restore.mutate(version.version)}
                              >
                                恢复为新版本
                              </Button>
                            </div>
                          ))}
                        </div>
                      ),
                    },
                  ]}
                />
              </div>
              <div className="infographic-editor-preview">
                <div className="infographic-editor-preview__heading">
                  <div>
                    <strong>实时预览</strong>
                    <span>{canvasSize.replace("x", " × ")}</span>
                  </div>
                  {current.overflow.length > 0 && (
                    <Tag color="error">
                      文字溢出 {current.overflow.length} 处
                    </Tag>
                  )}
                </div>
                <InfographicPreview
                  content={content}
                  template={template}
                  fontScale={fontScale}
                  brand={brand}
                  footer={footer}
                  backgroundUrl={current.background_url}
                  cssMode={workspace.use_css_background}
                  survey={Boolean(current.content_json.opinion_survey)}
                  renderedUrl={current.rendered_url}
                />
                {current.render_log.length > 0 && (
                  <Alert
                    type={
                      current.render_status === "rendered"
                        ? "success"
                        : "warning"
                    }
                    showIcon
                    title={`渲染状态：${current.render_status}`}
                    description={current.render_log.at(-1)?.message}
                  />
                )}
                {current.download_url && (
                  <Button
                    block
                    type="primary"
                    icon={<DownloadOutlined />}
                    href={current.download_url}
                  >
                    下载当前 PNG
                  </Button>
                )}
              </div>
            </div>
          </fieldset>
        )}
      </Drawer>
    </section>
  );
}
