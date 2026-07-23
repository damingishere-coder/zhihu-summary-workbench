import {
  CopyOutlined,
  DeleteOutlined,
  HistoryOutlined,
  PictureOutlined,
  ReloadOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Empty,
  Input,
  Popconfirm,
  Select,
  Space,
  Switch,
  Tabs,
  Tag,
  Upload,
} from "antd";
import { useState } from "react";
import { api } from "../api/client";
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
  if (!copied) {
    throw clipboardError ?? new Error("浏览器不支持复制");
  }
}

export function ImagePromptWorkspace({ draftId }: { draftId: string }) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [style, setStyle] = useState("克制的知识编辑插画");
  const query = useQuery({
    queryKey: ["image-workspace", draftId],
    queryFn: () => api.imageWorkspace(draftId),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["image-workspace", draftId] });
  };
  const generate = useMutation({
    mutationFn: () =>
      api.generateImagePrompt(draftId, { visual_style: style, aspect_ratio: "3:4" }),
    onSuccess: async () => {
      message.success("图片 Prompt 已生成并保存为新版本");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const markCopied = useMutation({
    mutationFn: ({ imageId, language }: { imageId: string; language: "zh" | "en" }) =>
      api.markImagePromptCopied(imageId, language),
    onSuccess: refresh,
  });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadVisualAsset(draftId, file),
    onSuccess: async () => {
      message.success("背景图已上传并保存为新版本");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const cssMode = useMutation({
    mutationFn: ({ imageId, enabled }: { imageId: string; enabled: boolean }) =>
      api.setImageCssMode(imageId, enabled),
    onSuccess: refresh,
    onError: (error) => message.error(error.message),
  });
  const remove = useMutation({
    mutationFn: (imageId: string) => api.deleteImageBackground(imageId),
    onSuccess: async () => {
      message.success("当前背景已移除，历史版本仍然保留");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });

  const workspace = query.data;
  const current = workspace?.current;
  const copy = async (language: "zh" | "en") => {
    if (!workspace || !current) return;
    const text = language === "zh" ? current.prompt_zh : current.prompt_en;
    try {
      await copyPromptText(text);
      message.success(language === "zh" ? "中文 Prompt 已复制" : "英文 Prompt 已复制");
      markCopied.mutate({ imageId: workspace.id, language });
    } catch {
      message.error("浏览器未允许复制，请选中文本后手动复制");
    }
  };

  return (
    <section className="image-prompt-workspace">
      <div className="section-heading">
        <div>
          <h2>图片 Prompt 与上传</h2>
          <p>在 ChatGPT 中手动生图，再把背景图上传回来。</p>
        </div>
        {workspace && <Tag color={current ? "blue" : "default"}>v{workspace.current_version}</Tag>}
      </div>
      <Alert
        type="info"
        showIcon
        title="不调用图片 API"
        description="未上传图片也不会阻塞审核；系统会保留纯 CSS 背景模式。"
      />
      <div className="prompt-toolbar">
        <Select
          value={style}
          aria-label="视觉风格"
          onChange={setStyle}
          options={[
            { value: "克制的知识编辑插画", label: "知识编辑插画" },
            { value: "低干扰的抽象几何拼贴", label: "抽象几何拼贴" },
            { value: "理性的数据叙事插画", label: "数据叙事插画" },
          ]}
        />
        <Button
          type="primary"
          icon={current ? <ReloadOutlined /> : <PictureOutlined />}
          loading={generate.isPending}
          onClick={() => generate.mutate()}
        >
          {current ? "重新生成 Prompt" : "生成图片 Prompt"}
        </Button>
      </div>
      {!current ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="生成后可复制中英文 Prompt，并上传手动生成的背景图"
        />
      ) : (
        <Tabs
          className="image-workspace-tabs"
          items={[
            {
              key: "content",
              label: "信息图文案",
              children: (
                <div className="infographic-copy">
                  <strong>{current.content_json.title}</strong>
                  <p>{current.content_json.one_line_conclusion}</p>
                  {(current.content_json.consensus ?? []).map((item) => (
                    <div key={item.title}>
                      <span>{item.title}</span>
                      <p>{item.description}</p>
                    </div>
                  ))}
                  <small>
                    建议尺寸 {current.content_json.suggested_size ?? "1080×1440"} ·
                    文字将由 HTML/CSS 准确渲染
                  </small>
                </div>
              ),
            },
            {
              key: "prompt",
              label: "图片 Prompt",
              children: (
                <div className="prompt-copy-panel">
                  <label>中文 Prompt</label>
                  <Input.TextArea readOnly autoSize={{ minRows: 8, maxRows: 14 }} value={current.prompt_zh} />
                  <Button icon={<CopyOutlined />} onClick={() => void copy("zh")}>
                    复制中文 Prompt
                  </Button>
                  <label>英文 Prompt</label>
                  <Input.TextArea readOnly autoSize={{ minRows: 8, maxRows: 14 }} value={current.prompt_en} />
                  <Button icon={<CopyOutlined />} onClick={() => void copy("en")}>
                    复制英文 Prompt
                  </Button>
                </div>
              ),
            },
            {
              key: "history",
              label: <><HistoryOutlined /> 历史 {workspace?.versions.length ?? 0}</>,
              children: (
                <div className="image-version-list">
                  {workspace?.versions.map((version) => (
                    <div key={version.id}>
                      <strong>v{version.version}</strong>
                      <span>{formatDateTime(version.created_at, true)}</span>
                      <Tag>{version.background_url ? "含背景图" : "纯 CSS"}</Tag>
                    </div>
                  ))}
                </div>
              ),
            },
          ]}
        />
      )}
      {workspace && current && (
        <div className="background-workflow">
          <div className="background-workflow__heading">
            <div>
              <strong>背景图</strong>
              <p>支持 PNG、JPEG、WebP，最大 10 MB。</p>
            </div>
            <Space>
              <span>纯 CSS</span>
              <Switch
                checked={workspace.use_css_background}
                loading={cssMode.isPending}
                onChange={(enabled) => cssMode.mutate({ imageId: workspace.id, enabled })}
              />
            </Space>
          </div>
          {current.background_url && !workspace.use_css_background && (
            <img
              className="uploaded-background-preview"
              src={current.background_url}
              alt="手动上传的 GPT 生成背景图预览"
            />
          )}
          <Space wrap>
            <Upload
              accept="image/png,image/jpeg,image/webp"
              showUploadList={false}
              customRequest={({ file, onSuccess, onError }) => {
                upload.mutate(file as File, {
                  onSuccess: () => onSuccess?.({}),
                  onError: (error) => onError?.(error),
                });
              }}
            >
              <Button icon={<UploadOutlined />} loading={upload.isPending}>
                {current.background_url ? "替换背景图" : "上传手动生成图片"}
              </Button>
            </Upload>
            {current.background_url && (
              <Popconfirm
                title="移除当前背景图？"
                description="历史版本和原始文件仍会保留。"
                onConfirm={() => remove.mutate(workspace.id)}
              >
                <Button danger icon={<DeleteOutlined />} loading={remove.isPending}>
                  移除背景
                </Button>
              </Popconfirm>
            )}
          </Space>
        </div>
      )}
    </section>
  );
}
