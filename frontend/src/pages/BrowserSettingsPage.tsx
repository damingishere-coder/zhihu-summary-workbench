import {
  CheckCircleOutlined,
  QrcodeOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Space, Tag } from "antd";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";

const pendingStates = new Set(["starting", "qr_ready", "scanned"]);

export function safeBrowserReturnPath(value: string | null) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/tasks";
}

export function shouldPollBrowserSession(state: string | undefined) {
  return pendingStates.has(state ?? "");
}

export function BrowserSettingsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const taskId = searchParams.get("taskId");
  const recoveryMode =
    searchParams.get("recovery") === "verification"
      ? "verification"
      : "login";
  const requestedReturnTo = searchParams.get("returnTo");
  const returnTo = safeBrowserReturnPath(requestedReturnTo);
  const attemptedResumeKeys = useRef(new Set<string>());
  const [resumeError, setResumeError] = useState<string | null>(null);

  const session = useQuery({
    queryKey: ["browser-session"],
    queryFn: api.browserSession,
    refetchInterval: (query) =>
      shouldPollBrowserSession(query.state.data?.state) ? 2_000 : false,
  });
  const start = useMutation({
    mutationFn: api.startBrowserSession,
    onSuccess: async (state) => {
      queryClient.setQueryData(["browser-session"], state);
      await queryClient.invalidateQueries({ queryKey: ["browser-session"] });
    },
    onError: (error) =>
      message.open({
        key: "browser-session-action",
        type: "error",
        content: error.message,
      }),
  });
  const refresh = useMutation({
    mutationFn: api.refreshBrowserSession,
    onSuccess: async (state) => {
      queryClient.setQueryData(["browser-session"], state);
      await queryClient.invalidateQueries({ queryKey: ["browser-session"] });
    },
    onError: (error) =>
      message.open({
        key: "browser-session-action",
        type: "error",
        content: error.message,
      }),
  });
  const recheck = useMutation({
    mutationFn: api.recheckBrowserSession,
    onSuccess: async (state) => {
      queryClient.setQueryData(["browser-session"], state);
      await queryClient.invalidateQueries({ queryKey: ["browser-session"] });
    },
    onError: (error) =>
      message.open({
        key: "browser-session-action",
        type: "error",
        content: error.message,
      }),
  });
  const resume = useMutation({
    mutationFn: ({
      id,
      mode,
    }: {
      id: string;
      mode: "login" | "verification";
    }) =>
      mode === "verification"
        ? api.resumeTaskAfterVerification(id)
        : api.resumeTaskAfterLogin(id),
    onSuccess: async () => {
      setResumeError(null);
      message.open({
        key: "browser-task-resume",
        type: "success",
        content:
          recoveryMode === "verification"
            ? "验证确认完成，原任务已重新入队"
            : "知乎登录成功，原任务已自动恢复",
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["questions"] }),
        queryClient.invalidateQueries({ queryKey: ["tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
      navigate(returnTo, { replace: true });
    },
    onError: async (error) => {
      setResumeError(error.message);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["browser-session"] }),
        queryClient.invalidateQueries({ queryKey: ["tasks"] }),
      ]);
    },
  });

  const autoResumeKey =
    session.data?.state === "authenticated" && taskId
      ? `${taskId}:${recoveryMode}:${session.data.updated_at}`
      : null;
  const resumeTask = resume.mutate;

  useEffect(() => {
    if (!autoResumeKey || !taskId) return;
    if (attemptedResumeKeys.current.has(autoResumeKey)) return;
    attemptedResumeKeys.current.add(autoResumeKey);
    setResumeError(null);
    resumeTask({ id: taskId, mode: recoveryMode });
  }, [autoResumeKey, recoveryMode, taskId, resumeTask]);

  const state = session.data;
  const authenticated = Boolean(state?.authenticated);
  const showQr = state?.state === "qr_ready" && state.qr_code_url;
  const canRecheck = ["expired", "verification_required", "failed"].includes(
    state?.state ?? "",
  );
  const refreshing =
    refresh.isPending || recheck.isPending || state?.state === "starting";

  return (
    <div className="page">
      <PageHeader
        title="知乎扫码登录"
        description="工作台使用独立的浏览器会话，不需要填写 Windows Chrome 目录。"
      />
      <Alert
        className="phase-alert"
        type="info"
        showIcon
        title="账号安全说明"
        description="这里只显示知乎官方登录二维码。账号密码不会经过工作台；登录会话只保存在本机 data 目录，不会提交到 Git。系统不会绕过验证码或平台风控。"
      />

      {session.isLoading && <LoadingBlock rows={8} />}
      {session.isError && (
        <ErrorState
          error={session.error}
          onRetry={() => void session.refetch()}
        />
      )}
      {state && (
        <section className="settings-section browser-settings-card browser-login-card">
          <div className="browser-login-card__status">
            <div>
              <h2>知乎登录会话</h2>
              <p>
                {state.state === "failed"
                  ? "本次登录检查未完成，请按下方提示处理后重试。"
                  : state.message}
              </p>
            </div>
            <Tag
              color={
                authenticated
                  ? "success"
                  : state.state === "failed"
                    ? "error"
                    : "warning"
              }
              icon={
                authenticated ? (
                  <CheckCircleOutlined />
                ) : (
                  <SafetyCertificateOutlined />
                )
              }
            >
              {authenticated
                ? state.state === "verification_required"
                  ? "已登录，等待验证"
                  : "已登录"
                : state.state === "scanned"
                  ? "等待手机确认"
                  : state.state === "qr_ready"
                    ? "等待扫码"
                    : "需要操作"}
            </Tag>
          </div>

          {showQr && (
            <div className="browser-login-card__qr">
              <img src={state.qr_code_url!} alt="知乎登录二维码" />
              <strong>请打开知乎 App，进入“我的”并点击右上角扫一扫</strong>
              <span>扫码后本页会自动检测登录状态并恢复任务。</span>
            </div>
          )}

          {state.state === "verification_required" && (
            <Alert
              type="warning"
              showIcon
              title="知乎要求人工验证"
              description={
                authenticated
                  ? "登录仍然有效，只是本次请求被知乎拦截。完成验证后点击“重新检查登录状态”，不需要重新扫码。"
                  : "请先在知乎 App 中完成安全验证，然后重新检查现有会话；只有确认登录失效时才需要扫码。"
              }
            />
          )}

          {state.state === "scanned" && (
            <Alert
              type="info"
              showIcon
              title="二维码已扫描"
              description="请回到知乎 App 点击“确认登录”，本页会自动完成检测并返回原任务，不需要刷新网页。"
            />
          )}

          {state.state === "failed" && (
            <Alert
              type="error"
              showIcon
              title="工作台浏览器操作失败"
              description={state.message}
            />
          )}

          {resumeError && taskId && (
            <Alert
              type="error"
              showIcon
              title="任务恢复失败"
              description={resumeError}
              action={
                authenticated ? (
                  <Button
                    size="small"
                    loading={resume.isPending}
                    onClick={() => {
                      setResumeError(null);
                      resume.mutate({ id: taskId, mode: recoveryMode });
                    }}
                  >
                    重新恢复任务
                  </Button>
                ) : undefined
              }
            />
          )}

          <Space wrap>
            {state.state === "idle" && (
              <Button
                type="primary"
                icon={<QrcodeOutlined />}
                loading={start.isPending}
                onClick={() => start.mutate()}
              >
                开始扫码登录
              </Button>
            )}
            {canRecheck && (
              <Button
                type="primary"
                icon={<SafetyCertificateOutlined />}
                loading={refreshing}
                onClick={() => recheck.mutate()}
              >
                重新检查登录状态
              </Button>
            )}
            {(state.state === "qr_ready" ||
              (state.state === "expired" && !authenticated)) && (
              <Button
                type="default"
                icon={<ReloadOutlined />}
                loading={refreshing}
                onClick={() => refresh.mutate()}
              >
                {state.state === "expired"
                  ? "确认已退出？重新扫码"
                  : "二维码失效？换一张"}
              </Button>
            )}
            {authenticated && !taskId && (
              <Button type="primary" onClick={() => navigate("/questions")}>
                返回问题池
              </Button>
            )}
            {authenticated && taskId && !resumeError && (
              <Button loading={resume.isPending} disabled>
                正在自动恢复任务
              </Button>
            )}
          </Space>
        </section>
      )}
    </div>
  );
}
