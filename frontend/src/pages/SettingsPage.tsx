import {
  ApiOutlined,
  CheckCircleFilled,
  CodeOutlined,
  DatabaseOutlined,
  FolderOpenOutlined,
  PictureOutlined,
  SaveOutlined,
  ThunderboltOutlined,
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
      <PageHeader title="设置" description="管理非敏感运行配置、模型角色和第一阶段工作流。" />
      <Segmented
        className="settings-segmented"
        value={section}
        onChange={handleSection}
        options={[
          { value: "general", label: "系统与工作流", icon: <CodeOutlined /> },
          { value: "ai", label: "AI 与模型", icon: <ApiOutlined /> },
        ]}
      />
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
                <InputNumber min={5} max={600} suffix="秒" />
              </Form.Item>
            </div>
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
              <div><h2>手动图片 Prompt 工作流</h2><p>本项目不会接入或保存 OpenAI 图片 API Key。</p></div>
            </div>
            <div className="settings-fields">
              <Form.Item label="图片生成模式">
                <Input value="复制 Prompt 到 ChatGPT 并手动上传" disabled />
              </Form.Item>
              <Form.Item label="手动上传">
                <Input value={query.data.allow_manual_image_upload ? "允许" : "关闭"} disabled />
              </Form.Item>
            </div>
          </section>
          <section className="settings-section">
            <div className="settings-section__heading">
              <FolderOpenOutlined />
              <div><h2>浏览器目录</h2><p>只保存路径引用，不读取账号密码、Cookie 或浏览器缓存。</p></div>
            </div>
            <Form.Item name="browser_user_data_dir" label="知乎浏览器用户数据目录">
              <Input placeholder="留空；第三阶段需要时由用户本地配置" />
            </Form.Item>
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
              type={query.data.deepseek_configured ? "success" : "info"}
              showIcon
              title={query.data.deepseek_configured ? "DeepSeek 密钥已在本机配置" : "当前未配置 DeepSeek 密钥"}
              description={
                query.data.deepseek_configured
                  ? "可以切换到真实模式并测试结构化输出。"
                  : "Mock 模式可完成全部第一阶段测试；如需真实调用，请只在本机 .env 设置 DEEPSEEK_API_KEY。"
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
                    { label: "DeepSeek 真实调用", value: "deepseek", disabled: !query.data.deepseek_configured },
                  ]}
                />
              </Form.Item>
              <div className="settings-fields settings-fields--three">
                <Form.Item name="fast_text_model" label="快速文本模型"><Input /></Form.Item>
                <Form.Item name="reasoning_model" label="推理模型"><Input /></Form.Item>
                <Form.Item name="fallback_text_model" label="备用文本模型"><Input /></Form.Item>
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
