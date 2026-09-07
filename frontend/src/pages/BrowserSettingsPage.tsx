import {
  ApiOutlined,
  CopyOutlined,
  DisconnectOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Descriptions, Space, Tag, Upload } from "antd";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import type { ImportBundleV1 } from "../types";
import { formatDateTime } from "../utils/format";

const MAX_IMPORT_BYTES = 6 * 1024 * 1024;

export function safeBrowserReturnPath(value: string | null) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/tasks";
}

export function shouldPollBrowserSession(state: string | undefined) {
  return state !== "unpaired";
}

function authLabel(value: string) {
  return {
    authenticated: "实时检查：已登录",
    login_required: "等待登录",
    verification_required: "等待人工验证",
    unknown: "尚未检查",
  }[value] ?? value;
}

function captureMethodLabel(value: string | null | undefined) {
  return {
    rendered_dom: "当前页面 DOM",
    same_origin_api: "显式同源 API",
    json_import: "人工 JSON 导入",
  }[value ?? ""] ?? value ?? "—";
}

function validateImportBundle(value: unknown): ImportBundleV1 {
  if (!value || typeof value !== "object") throw new Error("文件内容必须是 JSON 对象");
  const bundle = value as Partial<ImportBundleV1>;
  if (bundle.format !== "ImportBundleV1" || bundle.version !== 1) {
    throw new Error("只支持 ImportBundleV1 格式");
  }
  if (!bundle.question?.id || !/^\d+$/.test(bundle.question.id)) throw new Error("问题 id 无效");
  if (!Array.isArray(bundle.answers) || bundle.answers.length < 1 || bundle.answers.length > 500) {
    throw new Error("回答数量必须在 1 到 500 条之间");
  }
  const answerIds = bundle.answers.map((item) => item.id);
  if (answerIds.some((id) => !/^\d+$/.test(id))) throw new Error("存在无效回答 id");
  if (new Set(answerIds).size !== answerIds.length) throw new Error("文件中存在重复回答 id");
  if (bundle.answers.some((item) => item.question_id !== bundle.question!.id)) {
    throw new Error("存在不属于该问题的回答");
  }
  return bundle as ImportBundleV1;
}

export function BrowserSettingsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const taskId = searchParams.get("taskId");
  const returnTo = safeBrowserReturnPath(searchParams.get("returnTo"));
  const [bundle, setBundle] = useState<ImportBundleV1 | null>(null);

  const bridge = useQuery({
    queryKey: ["browser-bridge"],
    queryFn: api.browserBridgeStatus,
    refetchInterval: (query) =>
      shouldPollBrowserSession(query.state.data?.connection) ? 3_000 : false,
  });
  const task = useQuery({
    queryKey: ["tasks", taskId],
    queryFn: () => api.task(taskId!),
    enabled: Boolean(taskId),
  });
  const question = useQuery({
    queryKey: ["questions", task.data?.question_id],
    queryFn: () => api.question(task.data!.question_id),
    enabled: Boolean(task.data?.question_id),
  });
  const pairing = useMutation({
    mutationFn: api.createBridgePairing,
    onError: (error) => message.error(error.message),
  });
  const unpair = useMutation({
    mutationFn: api.unpairBridge,
    onSuccess: async (result) => {
      message.success(result.message);
      pairing.reset();
      await queryClient.invalidateQueries({ queryKey: ["browser-bridge"] });
    },
    onError: (error) => message.error(error.message),
  });
  const retry = useMutation({
    mutationFn: () => api.retryCollection(taskId!),
    onSuccess: async (result) => {
      message.success(result.message);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["browser-bridge"] }),
        queryClient.invalidateQueries({ queryKey: ["tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["questions"] }),
      ]);
    },
    onError: (error) => message.error(error.message),
  });
  const importMutation = useMutation({
    mutationFn: () => api.importAnswers(task.data!.question_id, bundle!),
    onSuccess: async (result) => {
      message.success(result.message);
      setBundle(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["questions"] }),
        queryClient.invalidateQueries({ queryKey: ["answers"] }),
        queryClient.invalidateQueries({ queryKey: ["analysis"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
      navigate(returnTo, { replace: true });
    },
    onError: (error) => message.error(error.message),
  });

  const state = bridge.data;
  const connected = state?.connection === "connected";
  const capability = connected && state.zhihu_auth === "authenticated"
    ? "可采集"
    : state?.zhihu_auth === "verification_required"
      ? "被知乎验证阻断"
      : "等待扩展/登录";

  return (
    <div className="page">
      <PageHeader
        title="Chrome 扩展桥接"
        description="在你正常登录知乎的 Chrome 标签页内采集；旧的独立扫码浏览器已经停用。"
      />
      <Alert
        className="phase-alert"
        type="info"
        showIcon
        title="账号数据边界"
        description="扩展只回传结构化问题和回答，不读取或上传 Cookie、密码和 Token。遇到验证码或风控时会诚实暂停，不会尝试绕过。"
      />

      {bridge.isLoading && <LoadingBlock rows={7} />}
      {bridge.isError && <ErrorState error={bridge.error} onRetry={() => void bridge.refetch()} />}
      {state && (
        <section className="settings-section browser-settings-card browser-login-card">
          <div className="browser-login-card__status">
            <div><h2>扩展与知乎实时状态</h2><p>{state.message}</p></div>
            <Tag color={connected ? "success" : "warning"} icon={<ApiOutlined />}>
              {connected ? "扩展已连接" : state.connection === "unpaired" ? "尚未配对" : "扩展已断开"}
            </Tag>
          </div>
          <Descriptions column={{ xs: 1, md: 2 }} size="small" bordered>
            <Descriptions.Item label="扩展连接">{state.connection}</Descriptions.Item>
            <Descriptions.Item label="知乎登录">{authLabel(state.zhihu_auth)}</Descriptions.Item>
            <Descriptions.Item label="采集能力">{capability}</Descriptions.Item>
            <Descriptions.Item label="扩展版本">{state.extension_version || "—"}</Descriptions.Item>
            <Descriptions.Item label="最近连接">{state.last_seen_at ? formatDateTime(state.last_seen_at, true) : "—"}</Descriptions.Item>
            <Descriptions.Item label="最近登录检查">{state.last_check_at ? formatDateTime(state.last_check_at, true) : "—"}</Descriptions.Item>
            <Descriptions.Item label="活动采集任务" span={2}>{state.active_job_id || "—"}</Descriptions.Item>
            <Descriptions.Item label="最近采集方式">
              {captureMethodLabel(state.latest_capture?.capture_method)}
            </Descriptions.Item>
            <Descriptions.Item label="最近采集数量">
              {state.latest_capture?.collected_answer_count ?? "—"} / 可见 {state.latest_capture?.visible_answer_count ?? "—"}
            </Descriptions.Item>
            {state.latest_capture?.page_url && (
              <Descriptions.Item label="最近采集页面" span={2}>
                <a href={state.latest_capture.page_url} target="_blank" rel="noreferrer">打开知乎问题页</a>
              </Descriptions.Item>
            )}
          </Descriptions>

          {state.latest_capture?.diagnostics?.filter((item) => item.level !== "info").map((item) => (
            <Alert
              key={`${item.code}-${item.message}`}
              type={item.level === "error" ? "error" : "warning"}
              showIcon
              title={item.message}
            />
          ))}

          {pairing.data && (
            <Alert
              type="success"
              showIcon
              title={`一次性配对码：${pairing.data.pairing_code}`}
              description={`请在 ${formatDateTime(pairing.data.expires_at, true)} 前打开扩展弹窗并粘贴。此码只能使用一次。`}
              action={<Button size="small" icon={<CopyOutlined />} onClick={() => {
                void navigator.clipboard.writeText(pairing.data.pairing_code);
                message.success("配对码已复制");
              }}>复制</Button>}
            />
          )}

          <Space wrap>
            <Button type="primary" icon={<SafetyCertificateOutlined />} loading={pairing.isPending} onClick={() => pairing.mutate()}>
              生成一次性配对码
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => void bridge.refetch()}>刷新实时状态</Button>
            {state.connection !== "unpaired" && (
              <Button danger icon={<DisconnectOutlined />} loading={unpair.isPending} onClick={() => unpair.mutate()}>撤销配对</Button>
            )}
            {taskId && (
              <Button type="primary" loading={retry.isPending} onClick={() => retry.mutate()}>用 Chrome 重新获取并继续</Button>
            )}
          </Space>
        </section>
      )}

      {taskId && (
        <section className="settings-section browser-settings-card">
          <h2>知乎仍阻断时：人工 JSON 兜底</h2>
          <p>导入会明确记录为人工来源，只能证明后半段流水线，不会冒充实时自动采集成功。</p>
          <Space wrap>
            <Upload
              accept="application/json,.json"
              maxCount={1}
              showUploadList={false}
              beforeUpload={async (file) => {
                try {
                  if (file.size > MAX_IMPORT_BYTES) throw new Error("文件超过 6 MiB 上限");
                  const parsed = validateImportBundle(JSON.parse(await file.text()));
                  if (question.data?.external_id && parsed.question.id !== question.data.external_id) {
                    throw new Error("导入文件的问题 id 与当前任务不一致");
                  }
                  setBundle(parsed);
                } catch (error) {
                  message.error(error instanceof Error ? error.message : "无法读取 JSON 文件");
                }
                return false;
              }}
            ><Button icon={<UploadOutlined />}>选择 ImportBundleV1 JSON</Button></Upload>
            {bundle && (
              <Button type="primary" loading={importMutation.isPending} onClick={() => importMutation.mutate()}>
                确认导入 {bundle.answers.length} 条回答
              </Button>
            )}
          </Space>
          {bundle && (
            <Alert
              type="warning"
              showIcon
              title={`预览：${bundle.question.title}`}
              description={`问题 ${bundle.question.id}，${bundle.answers.length} 条回答，采集时间 ${formatDateTime(bundle.collected_at, true)}。确认后会恢复当前任务。`}
            />
          )}
        </section>
      )}
    </div>
  );
}
