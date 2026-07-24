import {
  HistoryOutlined,
  PlayCircleOutlined,
  RollbackOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Input,
  Select,
  Table,
  Tag,
} from "antd";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import type { PromptVersion } from "../types";
import { formatDateTime } from "../utils/format";

export function PromptsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const prompts = useQuery({ queryKey: ["prompts"], queryFn: api.prompts });
  const [selectedId, setSelectedId] = useState("");
  const selected = prompts.data?.find((item) => item.id === selectedId) ?? prompts.data?.[0];
  const versions = useQuery({
    queryKey: ["prompt-versions", selected?.id],
    queryFn: () => api.promptVersions(selected!.id),
    enabled: Boolean(selected),
  });
  const [content, setContent] = useState("");
  const [role, setRole] = useState<PromptVersion["model_role"]>("fast_text_model");
  const [changeNote, setChangeNote] = useState("");
  const [testInput, setTestInput] = useState('{"question_title":"如何建立稳定习惯？"}');
  const [testOutput, setTestOutput] = useState("");
  useEffect(() => {
    if (!selected?.active) return;
    setSelectedId(selected.id);
    setContent(selected.active.content);
    setRole(selected.active.model_role);
    setChangeNote("");
    setTestOutput("");
  }, [selected?.id, selected?.active_version]);
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["prompts"] }),
      queryClient.invalidateQueries({ queryKey: ["prompt-versions", selected?.id] }),
    ]);
  };
  const save = useMutation({
    mutationFn: () => api.updatePrompt(selected!.id, {
      content,
      variables: selected?.active?.variables ?? [],
      model_role: role,
      parameters: selected?.active?.parameters ?? {},
      change_note: changeNote,
    }),
    onSuccess: async (version) => {
      message.success(`已创建不可覆盖的 Prompt v${version.version}`);
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const rollback = useMutation({
    mutationFn: (version: number) => api.activatePrompt(selected!.id, version, "运营人员从版本列表回滚"),
    onSuccess: async () => {
      message.success("活动版本已切换，历史内容没有被覆盖");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const test = useMutation({
    mutationFn: () => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(testInput) as Record<string, unknown>;
      } catch {
        throw new Error("测试输入不是有效 JSON");
      }
      return api.testPrompt(selected!.id, selected?.active_version, parsed);
    },
    onSuccess: (result) => {
      setTestOutput(result.output);
      message.success(`测试完成：${result.model} · ${result.duration_ms} ms`);
    },
    onError: (error) => message.error(error.message),
  });

  return (
    <div className="page">
      <PageHeader title="Prompt 管理" description="每次修改都创建新版本；可测试、切换活动版本、回滚并保留审计记录。" />
      <Alert className="phase-alert" type="info" showIcon title="Prompt 不会原地覆盖" description="保存只会新增版本。流水线每次调用都会读取当前活动版本，回滚也只切换活动指针。" />
      {prompts.isLoading && <LoadingBlock rows={12} />}
      {prompts.isError && <ErrorState error={prompts.error} onRetry={() => void prompts.refetch()} />}
      {selected && (
        <div className="prompt-manager-layout">
          <aside className="work-surface prompt-template-list">
            {prompts.data?.map((item) => (
              <button
                type="button"
                className={item.id === selected.id ? "prompt-template-item prompt-template-item--active" : "prompt-template-item"}
                key={item.id}
                onClick={() => setSelectedId(item.id)}
              >
                <strong>{item.name}</strong>
                <span>{item.key}</span>
                <Tag>v{item.active_version} / {item.version_count}</Tag>
              </button>
            ))}
          </aside>
          <section className="work-surface prompt-editor">
            <div className="section-heading">
              <div><h2>{selected.name}</h2><p>{selected.description}</p></div>
              <Tag color="blue">活动 v{selected.active_version}</Tag>
            </div>
            <label>模型角色</label>
            <Select value={role} onChange={setRole} options={[
              { value: "fast_text_model", label: "快速文本模型" },
              { value: "reasoning_model", label: "推理模型" },
              { value: "fallback_text_model", label: "备用文本模型" },
            ]} />
            <label>Prompt 内容</label>
            <Input.TextArea className="prompt-code-editor" value={content} autoSize={{ minRows: 16, maxRows: 28 }} onChange={(event) => setContent(event.target.value)} />
            <label>变更说明（必填）</label>
            <Input value={changeNote} maxLength={1000} placeholder="说明为什么修改，便于审计和回滚" onChange={(event) => setChangeNote(event.target.value)} />
            <Button type="primary" icon={<SaveOutlined />} disabled={!changeNote.trim() || content.length < 10} loading={save.isPending} onClick={() => save.mutate()}>
              保存为新版本
            </Button>
          </section>
          <aside className="work-surface prompt-test-panel">
            <h2><PlayCircleOutlined /> 测试当前版本</h2>
            <label>测试输入 JSON</label>
            <Input.TextArea value={testInput} autoSize={{ minRows: 7, maxRows: 12 }} onChange={(event) => setTestInput(event.target.value)} />
            <Button block icon={<PlayCircleOutlined />} loading={test.isPending} onClick={() => test.mutate()}>运行 Mock / 当前 Provider 测试</Button>
            {testOutput && <pre className="prompt-test-output">{testOutput}</pre>}
            <h3><HistoryOutlined /> 版本历史</h3>
            <Table
              size="small"
              rowKey="id"
              loading={versions.isLoading}
              dataSource={versions.data}
              pagination={false}
              columns={[
                { title: "版本", dataIndex: "version", width: 58, render: (value: number) => `v${value}` },
                { title: "说明", dataIndex: "change_note", ellipsis: true },
                { title: "时间", dataIndex: "created_at", width: 118, render: (value: string) => formatDateTime(value, true) },
                {
                  title: "",
                  width: 68,
                  render: (_: unknown, item: PromptVersion) => (
                    <Button
                      size="small"
                      type="text"
                      icon={<RollbackOutlined />}
                      disabled={item.version === selected.active_version}
                      loading={rollback.isPending}
                      onClick={() => rollback.mutate(item.version)}
                    >
                      回滚
                    </Button>
                  ),
                },
              ]}
            />
          </aside>
        </div>
      )}
    </div>
  );
}
