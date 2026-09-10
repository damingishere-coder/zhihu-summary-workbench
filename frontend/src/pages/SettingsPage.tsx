import {
  ApiOutlined,
  CheckCircleFilled,
  CodeOutlined,
  DatabaseOutlined,
  PictureOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Divider,
  Form,
  Input,
  InputNumber,
  Radio,
  Segmented,
  Space,
  Spin,
  Tag,
} from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import type { ModelTestResult, PublicSettings } from "../types";

export function SettingsPage({
  initialSection = "general",
}: {
  initialSection?: "general" | "ai";
}) {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [section, setSection] = useState(initialSection);
  const [form] = Form.useForm();
  const [testForm] = Form.useForm();
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null);
  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  useEffect(() => {
    if (query.data) form.setFieldsValue(query.data);
  }, [form, query.data]);
  const save = useMutation({
    mutationFn: (values: Partial<PublicSettings>) => api.updateSettings(values),
    onSuccess: async (settings) => {
      form.setFieldsValue(settings);
      message.success("设置已保存");
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) => message.error(error.message),
  });
  const modelTest = useMutation({
    mutationFn: api.testModel,
    onSuccess: (result) => {
      setTestResult(result);
      message.success("模型测试通过");
    },
    onError: (error) => {
      setTestResult(null);
      message.error(error.message);
    },
  });
  const handleSection = (value: string | number) => {
    const next = String(value) as "general" | "ai";
    setSection(next);
    navigate(next === "ai" ? "/settings/ai" : "/settings", { replace: true });
  };

  return (
    <div className="page page--settings">
      <PageHeader title="设置" description="管理非敏感运行配置、模型角色、采集和手动图片工作流。" />
      <Segmented
        className="settings-segmented"
        value={section}
        onChange={handleSection}
        options={[
          { value: "general", label: "系统与工作流", icon: <CodeOutlined /> },
          { value: "ai", label: "AI 与模型", icon: <ApiOutlined /> },
        ]}
      />
      <Space wrap className="settings-shortcuts">
        <Button icon={<HistoryOutlined />} onClick={() => navigate("/prompts")}>Prompt 版本管理</Button>
        <Button icon={<SafetyCertificateOutlined />} onClick={() => navigate("/settings/browser")}>浏览器安全设置</Button>
        <Button onClick={() => navigate("/settings/open-source")}>开源组件与许可证</Button>
      </Space>
      {query.isLoading && <LoadingBlock rows={14} />}
      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {query.data && section === "general" && (
        <Form
          form={form}
          layout="vertical"
          className="settings-form"
          onFinish={(values) => save.mutate(values)}
        >
          <section className="settings-section">
            <div className="settings-section__heading">
              <ThunderboltOutlined />
              <div><h2>每日任务</h2><p>立即执行和后续定时任务会共用这些限制。</p></div>
            </div>
            <div className="settings-fields settings-fields--three">
              <Form.Item name="daily_question_limit" label="每日问题数" rules={[{ required: true }]}>
                <InputNumber min={1} max={100} suffix="个" />
              </Form.Item>
              <Form.Item name="max_ai_concurrency" label="最大 AI 并发" rules={[{ required: true }]}>
                <InputNumber min={1} max={20} suffix="个" />
              </Form.Item>
              <Form.Item name="request_timeout_seconds" label="请求超时" rules={[{ required: true }]}>
                <InputNumber min={5} max={1800} suffix="秒" />
              </Form.Item>
              <Form.Item name="hot_question_quota" label="热门问题配额" rules={[{ required: true }]}>
                <InputNumber min={0} max={100} suffix="个" />
              </Form.Item>
              <Form.Item name="manual_question_quota" label="手动问题配额" rules={[{ required: true }]}>
                <InputNumber min={0} max={100} suffix="个" />
              </Form.Item>
              <Form.Item name="max_answers_per_question" label="手动采样回答上限（今日计划按 30 分钟采集）" rules={[{ required: true }]}>
                <InputNumber min={1} max={500} suffix="条" />
              </Form.Item>
              <Form.Item name="daily_plan_time" label="历史计划时间（手动模式不生效）" rules={[{ required: true }]}>
                <Input disabled />
              </Form.Item>
              <Form.Item name="daily_publish_limit" label="每日发布上限" rules={[{ required: true }]}>
                <InputNumber min={1} max={100} suffix="篇" />
              </Form.Item>
              <Form.Item name="publish_interval_minutes" label="最小发布间隔" rules={[{ required: true }]}>
                <InputNumber min={5} max={1440} suffix="分钟" />
              </Form.Item>
            </div>
            <Alert
              type="info"
              showIcon
              title="自动开关保持关闭"
              description="RunDock 托管、手动启动。进入工作台后点击执行计划才开始生产；重启后手动继续。最终在知乎人工发布。"
            />
          </section>
          <section className="settings-section">
            <div className="settings-section__heading">
              <DatabaseOutlined />
              <div><h2>Embedding</h2><p>第二阶段可替换为正式多语言模型。</p></div>
            </div>
            <div className="settings-fields">
              <Form.Item label="Provider">
                <Input value={query.data.embedding_provider} disabled />
              </Form.Item>
              <Form.Item name="embedding_model" label="模型标识">
                <Input />
              </Form.Item>
            </div>
          </section>
          <section className="settings-section">
            <div className="settings-section__heading">
              <PictureOutlined />
              <div><h2>Codex 图片工作流</h2><p>使用已登录的 Codex CLI 内置生图，再由工作台排版中文。</p></div>
            </div>
            <div className="settings-fields">
              <Form.Item label="图片生成模式">
                <Input value="今日计划自动生成背景与 PNG；支持手动替换背景" disabled />
              </Form.Item>
              <Form.Item label="手动上传">
                <Input value={query.data.allow_manual_image_upload ? "允许" : "关闭"} disabled />
              </Form.Item>
            </div>
          </section>
          <div className="settings-actions">
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={save.isPending}>
              保存系统设置
            </Button>
          </div>
        </Form>
      )}
      {query.data && section === "ai" && (
        <div className="settings-form">
          <section className="settings-section">
            <div className="settings-section__heading">
              <ApiOutlined />
              <div><h2>Provider 模式</h2><p>密钥只能从本机环境读取，页面和 API 永不回显。</p></div>
            </div>
            <Alert
              type={query.data.codex_configured ? "success" : "warning"}
              showIcon
              title={query.data.codex_configured ? "Codex CLI 已找到并复用本机登录态" : "Codex CLI 尚未就绪"}
              description={
                query.data.codex_configured
                  ? "可以使用套餐内 Codex 用量执行本地批处理；DeepSeek 继续作为手动回退选项。"
                  : "请先安装并登录 Codex；在此之前可继续使用 Mock，或手动选择已配置的 DeepSeek。"
              }
            />
            <Form
              form={form}
              layout="vertical"
              className="settings-inner-form"
              onFinish={(values) => save.mutate(values)}
            >
              <Form.Item name="provider_mode" label="当前模式">
                <Radio.Group
                  optionType="button"
                  buttonStyle="solid"
                  options={[
                    { label: "Mock（推荐开发）", value: "mock" },
                    { label: "Codex CLI（推荐本机）", value: "codex", disabled: !query.data.codex_configured },
                    { label: "DeepSeek 真实调用", value: "deepseek", disabled: !query.data.deepseek_configured },
                  ]}
                />
              </Form.Item>
              <Form.Item name="codex_model" label="Codex 模型"><Input /></Form.Item>
              <div className="settings-fields settings-fields--three">
                <Form.Item name="fast_text_model" label="DeepSeek 快速模型（回退）"><Input /></Form.Item>
                <Form.Item name="reasoning_model" label="DeepSeek 推理模型（回退）"><Input /></Form.Item>
                <Form.Item name="fallback_text_model" label="DeepSeek 备用模型"><Input /></Form.Item>
              </div>
              <div className="settings-fields settings-fields--three">
                <Form.Item name="daily_model_budget" label="每日模型预算（0 表示不限）">
                  <InputNumber min={0} max={1000000} precision={2} prefix="¥" />
                </Form.Item>
                <Form.Item name="pause_on_budget_exceeded" label="超预算自动暂停">
                  <Radio.Group options={[{ label: "开启", value: true }, { label: "关闭", value: false }]} />
                </Form.Item>
                <Form.Item name="response_cache_enabled" label="结构化响应缓存">
                  <Radio.Group options={[{ label: "开启", value: true }, { label: "关闭", value: false }]} />
                </Form.Item>
              </div>
              <Space>
                <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={save.isPending}>
                  保存模型角色
                </Button>
                <Tag color={query.data.provider_mode === "mock" ? "blue" : "green"}>
                  当前：{query.data.provider_mode.toUpperCase()}
                </Tag>
              </Space>
            </Form>
          </section>
          <section className="settings-section model-test">
            <div className="settings-section__heading">
              <ThunderboltOutlined />
              <div><h2>结构化输出测试</h2><p>验证 Provider 请求、JSON 校验、Token 统计和耗时记录。</p></div>
            </div>
            <Form
              form={testForm}
              layout="vertical"
              initialValues={{
                provider_mode: query.data.provider_mode,
                question_title: "如何更高效地学习一项新技能？",
                sample_answer: "先明确目标，再拆成每天可以练习的小步骤。持续获得反馈，比一次学习很久更重要。",
              }}
              onFinish={(values) => modelTest.mutate(values)}
            >
              <div className="settings-fields">
                <Form.Item name="provider_mode" label="测试 Provider">
                  <Radio.Group
                    options={[
                      { label: "Mock", value: "mock" },
                      { label: "Codex CLI", value: "codex", disabled: !query.data.codex_configured },
                      { label: "DeepSeek", value: "deepseek", disabled: !query.data.deepseek_configured },
                    ]}
                  />
                </Form.Item>
                <Form.Item name="question_title" label="测试问题" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </div>
              <Form.Item name="sample_answer" label="测试回答" rules={[{ required: true }]}>
                <Input.TextArea rows={4} />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<ThunderboltOutlined />} loading={modelTest.isPending}>
                运行模型测试
              </Button>
            </Form>
            {modelTest.isPending && <Spin className="model-test__spin" />}
            {testResult && (
              <div className="model-test__result" aria-live="polite">
                <div className="model-test__result-title">
                  <CheckCircleFilled />
                  <strong>{testResult.message}</strong>
                  <Tag color="success">{testResult.provider} · {testResult.model}</Tag>
                </div>
                <p>{testResult.analysis?.summary}</p>
                <ul>{testResult.analysis?.core_claims.map((item) => <li key={item}>{item}</li>)}</ul>
                <Divider />
                <Space separator={<Divider orientation="vertical" />}>
                  <span>输入 {testResult.usage?.input_tokens ?? 0} tokens</span>
                  <span>输出 {testResult.usage?.output_tokens ?? 0} tokens</span>
                  <span>耗时 {testResult.usage?.duration_ms ?? 0} ms</span>
                  <span>估算费用 ¥{testResult.usage?.estimated_cost ?? 0}</span>
                </Space>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
