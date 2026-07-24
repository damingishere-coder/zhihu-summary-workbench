import { SafetyCertificateOutlined, SaveOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Input, Space, Tag } from "antd";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";

export function BrowserSettingsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const safety = useQuery({ queryKey: ["browser-safety"], queryFn: api.browserSafety, enabled: false });
  const [path, setPath] = useState("");
  useEffect(() => setPath(settings.data?.browser_user_data_dir ?? ""), [settings.data]);
  const save = useMutation({
    mutationFn: () => api.updateSettings({ browser_user_data_dir: path }),
    onSuccess: async () => {
      message.success("浏览器目录引用已保存；没有保存 Cookie、密码或 Token");
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error) => message.error(error.message),
  });
  return (
    <div className="page">
      <PageHeader title="浏览器安全设置" description="仅配置本机 Chrome 用户数据目录；所有外部发布仍要求人工确认。" />
      <Alert className="phase-alert" type="warning" showIcon title="安全边界" description="系统不会绕过登录、验证码或知乎风控。检测到任一情况时只暂停、截图并记录原因；自动发布默认关闭。" />
      {settings.isLoading && <LoadingBlock rows={8} />}
      {settings.isError && <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />}
      {settings.data && (
        <section className="settings-section browser-settings-card">
          <h2>Chrome 用户数据目录</h2>
          <p>此处只保存路径字符串。请不要粘贴账号、密码、Cookie、Token 或任何密钥。</p>
          <Input value={path} placeholder="例如：C:\Users\你的用户名\AppData\Local\Google\Chrome\User Data" onChange={(event) => setPath(event.target.value)} />
          <Space wrap>
            <Button type="primary" icon={<SaveOutlined />} loading={save.isPending} onClick={() => save.mutate()}>保存目录引用</Button>
            <Button icon={<SafetyCertificateOutlined />} loading={safety.isFetching} onClick={() => void safety.refetch()}>运行安全检查</Button>
          </Space>
          {safety.data && (
            <Alert
              type={safety.data.safe_to_continue ? "success" : "warning"}
              showIcon
              title={<Space>{safety.data.message}<Tag>{safety.data.state}</Tag></Space>}
              description={safety.data.safe_to_continue ? "目录可用；真正执行前仍会再次检查登录和验证码。" : "系统保持人工发布模式，没有继续操作知乎页面。"}
            />
          )}
        </section>
      )}
    </div>
  );
}
