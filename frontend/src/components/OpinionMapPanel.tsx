import {
  BranchesOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Checkbox,
  Collapse,
  Drawer,
  Empty,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tag,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { AnalysisOverview, ClaimCluster } from "../types";

function MapSection({
  title,
  values,
  tone,
}: {
  title: string;
  values: string[];
  tone: "success" | "warning" | "info" | "neutral";
}) {
  return (
    <section className={`opinion-section opinion-section--${tone}`}>
      <h3>{title}</h3>
      {values.length ? (
        <ul>{values.map((value, index) => <li key={`${title}-${index}`}>{value}</li>)}</ul>
      ) : (
        <p>暂无</p>
      )}
    </section>
  );
}

type ClusterDraft = Pick<
  ClaimCluster,
  | "name"
  | "summary"
  | "cluster_type"
  | "is_mainstream"
  | "is_minority"
  | "is_controversial"
  | "sort_order"
  | "write_policy"
>;

function ClusterEditor({
  cluster,
  selected,
  busy,
  onSelected,
  onSave,
  onSplit,
  onReanalyze,
  onDelete,
}: {
  cluster: ClaimCluster;
  selected: boolean;
  busy: boolean;
  onSelected: (checked: boolean) => void;
  onSave: (payload: ClusterDraft) => void;
  onSplit: () => void;
  onReanalyze: () => void;
  onDelete: () => void;
}) {
  const [draft, setDraft] = useState<ClusterDraft>({
    name: cluster.name,
    summary: cluster.summary,
    cluster_type: cluster.cluster_type,
    is_mainstream: cluster.is_mainstream,
    is_minority: cluster.is_minority,
    is_controversial: cluster.is_controversial,
    sort_order: cluster.sort_order,
    write_policy: cluster.write_policy,
  });
  useEffect(() => {
    setDraft({
      name: cluster.name,
      summary: cluster.summary,
      cluster_type: cluster.cluster_type,
      is_mainstream: cluster.is_mainstream,
      is_minority: cluster.is_minority,
      is_controversial: cluster.is_controversial,
      sort_order: cluster.sort_order,
      write_policy: cluster.write_policy,
    });
  }, [cluster]);

  return (
    <article className="cluster-editor-card">
      <div className="cluster-editor-card__header">
        <Checkbox checked={selected} onChange={(event) => onSelected(event.target.checked)}>
          选择合并
        </Checkbox>
        <Tag>{cluster.support_count} 个来源</Tag>
      </div>
      <label>观点簇名称</label>
      <Input
        value={draft.name}
        onChange={(event) => setDraft((value) => ({ ...value, name: event.target.value }))}
      />
      <label>代表总结</label>
      <Input.TextArea
        autoSize={{ minRows: 2, maxRows: 5 }}
        value={draft.summary}
        onChange={(event) => setDraft((value) => ({ ...value, summary: event.target.value }))}
      />
      <div className="cluster-editor-card__fields">
        <Select
          aria-label="观点类型"
          value={draft.cluster_type}
          onChange={(cluster_type) => setDraft((value) => ({ ...value, cluster_type }))}
          options={[
            { value: "consensus", label: "共识" },
            { value: "disagreement", label: "分歧" },
            { value: "minority", label: "少数派" },
            { value: "condition", label: "适用条件" },
          ]}
        />
        <Select
          aria-label="写入策略"
          value={draft.write_policy}
          onChange={(write_policy) => setDraft((value) => ({ ...value, write_policy }))}
          options={[
            { value: "auto", label: "自动判断" },
            { value: "force", label: "强制写入" },
            { value: "exclude", label: "禁止写入" },
          ]}
        />
        <InputNumber
          aria-label="观点顺序"
          min={0}
          max={10_000}
          value={draft.sort_order}
          onChange={(sort_order) =>
            setDraft((value) => ({ ...value, sort_order: Number(sort_order ?? 0) }))
          }
        />
      </div>
      <Space wrap size={[12, 4]}>
        <Checkbox
          checked={draft.is_mainstream}
          onChange={(event) =>
            setDraft((value) => ({ ...value, is_mainstream: event.target.checked }))
          }
        >
          主流
        </Checkbox>
        <Checkbox
          checked={draft.is_minority}
          onChange={(event) =>
            setDraft((value) => ({ ...value, is_minority: event.target.checked }))
          }
        >
          少数派
        </Checkbox>
        <Checkbox
          checked={draft.is_controversial}
          onChange={(event) =>
            setDraft((value) => ({ ...value, is_controversial: event.target.checked }))
          }
        >
          有争议
        </Checkbox>
      </Space>
      <Collapse
        ghost
        size="small"
        items={[
          {
            key: "sources",
            label: `查看来源回答 ${cluster.sources.length}`,
            children: (
              <div className="cluster-source-list">
                {cluster.sources.map((source) => (
                  <div key={source.answer_id}>
                    <a href={source.answer_url} target="_blank" rel="noreferrer">
                      {source.author_name}
                    </a>
                    <p>{source.excerpt}</p>
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
      <Space wrap>
        <Button
          type="primary"
          size="small"
          loading={busy}
          disabled={!draft.name.trim() || !draft.summary.trim()}
          onClick={() => onSave(draft)}
        >
          保存修改
        </Button>
        <Button size="small" icon={<ReloadOutlined />} loading={busy} onClick={onReanalyze}>
          局部重新分析
        </Button>
        <Button size="small" disabled={cluster.claim_ids.length < 2} onClick={onSplit}>
          拆分观点簇
        </Button>
        <Popconfirm
          title="删除这个观点簇？"
          description="删除后需要重新生成观点地图。"
          okText="删除"
          cancelText="取消"
          onConfirm={onDelete}
        >
          <Button size="small" danger icon={<DeleteOutlined />} loading={busy}>
            删除
          </Button>
        </Popconfirm>
      </Space>
    </article>
  );
}

export function OpinionMapPanel({
  analysis,
  onChanged,
}: {
  analysis: AnalysisOverview | undefined;
  onChanged: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [mapStale, setMapStale] = useState(false);
  const [splitTarget, setSplitTarget] = useState<ClaimCluster | null>(null);
  const [splitName, setSplitName] = useState("");
  const [splitClaimIds, setSplitClaimIds] = useState<string[]>([]);

  const finishClusterChange = async (text: string) => {
    message.success(text);
    setMapStale(true);
    setSelectedIds([]);
    await onChanged();
  };
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ClusterDraft }) =>
      api.updateCluster(id, payload),
    onSuccess: () => finishClusterChange("观点簇已更新"),
    onError: (error) => message.error(error.message),
  });
  const mergeMutation = useMutation({
    mutationFn: () => api.mergeClusters(selectedIds),
    onSuccess: () => finishClusterChange("所选观点簇已合并"),
    onError: (error) => message.error(error.message),
  });
  const splitMutation = useMutation({
    mutationFn: () => api.splitCluster(splitTarget!.id, splitClaimIds, splitName),
    onSuccess: async () => {
      setSplitTarget(null);
      setSplitName("");
      setSplitClaimIds([]);
      await finishClusterChange("观点簇已拆分");
    },
    onError: (error) => message.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: api.deleteCluster,
    onSuccess: () => finishClusterChange("观点簇已删除"),
    onError: (error) => message.error(error.message),
  });
  const reanalyzeMutation = useMutation({
    mutationFn: api.reanalyzeCluster,
    onSuccess: () => finishClusterChange("观点簇已局部重新分析"),
    onError: (error) => message.error(error.message),
  });
  const mapMutation = useMutation({
    mutationFn: () => api.regenerateOpinionMap(analysis!.question_id),
    onSuccess: async () => {
      message.success("观点地图已按当前编辑结果重新生成");
      setMapStale(false);
      await onChanged();
    },
    onError: (error) => message.error(error.message),
  });
  const busyIds = useMemo(
    () =>
      new Set(
        [
          updateMutation.variables?.id,
          deleteMutation.variables,
          reanalyzeMutation.variables,
        ].filter(Boolean),
      ),
    [deleteMutation.variables, reanalyzeMutation.variables, updateMutation.variables?.id],
  );

  if (!analysis?.opinion_map) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="观点聚类完成后会生成共识与分歧地图"
      />
    );
  }
  const map = analysis.opinion_map;
  return (
    <div className="opinion-map">
      <div className="opinion-map__toolbar">
        <Button size="small" icon={<EditOutlined />} onClick={() => setDrawerOpen(true)}>
          编辑观点簇
        </Button>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={mapMutation.isPending}
          onClick={() => mapMutation.mutate()}
        >
          重建观点地图
        </Button>
      </div>
      {mapStale && (
        <Alert
          type="warning"
          showIcon
          title="观点簇已修改"
          description="点击“重建观点地图”后，新顺序和写入策略才会进入文章生成。"
        />
      )}
      <div className="opinion-map__answer">
        <span><BranchesOutlined /> 一句话结论</span>
        <strong>{map.one_sentence_answer}</strong>
      </div>
      <div className="cluster-chips">
        {analysis.clusters.map((cluster) => (
          <Tag
            key={cluster.id}
            color={
              cluster.write_policy === "exclude"
                ? "default"
                : cluster.write_policy === "force"
                  ? "processing"
                  : cluster.cluster_type === "consensus"
                    ? "success"
                    : cluster.cluster_type === "disagreement"
                      ? "warning"
                      : "blue"
            }
          >
            {cluster.name} · {cluster.support_count} 来源
          </Tag>
        ))}
      </div>
      <MapSection title="主流共识" values={map.main_consensus} tone="success" />
      <MapSection title="主要分歧" values={map.main_disagreements} tone="warning" />
      <MapSection title="少数派但有价值" values={map.minority_but_valuable_views} tone="info" />
      <MapSection title="适用条件" values={map.applicable_conditions} tone="neutral" />
      <div className="opinion-map__footer">
        <span><CheckCircleOutlined /> {analysis.answers_included} 条回答纳入分析</span>
        <span><SafetyCertificateOutlined /> {analysis.clusters.length} 个观点簇</span>
        <span><ExclamationCircleOutlined /> 所有结论需人工核验来源</span>
      </div>

      <Drawer
        title="编辑观点簇"
        size={620}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Button
            type="primary"
            disabled={selectedIds.length < 2}
            loading={mergeMutation.isPending}
            onClick={() => mergeMutation.mutate()}
          >
            合并所选（{selectedIds.length}）
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          title="修改后请重建观点地图"
          description="顺序数字越小越靠前；强制写入和禁止写入会约束后续观点地图与文章。"
        />
        <div className="cluster-editor-list">
          {analysis.clusters.map((cluster) => (
            <ClusterEditor
              key={cluster.id}
              cluster={cluster}
              selected={selectedIds.includes(cluster.id)}
              busy={busyIds.has(cluster.id)}
              onSelected={(checked) =>
                setSelectedIds((values) =>
                  checked
                    ? [...new Set([...values, cluster.id])]
                    : values.filter((value) => value !== cluster.id),
                )
              }
              onSave={(payload) => updateMutation.mutate({ id: cluster.id, payload })}
              onSplit={() => {
                setSplitTarget(cluster);
                setSplitName(`${cluster.name}（拆分）`);
                setSplitClaimIds(cluster.claim_ids.slice(0, 1));
              }}
              onReanalyze={() => reanalyzeMutation.mutate(cluster.id)}
              onDelete={() => deleteMutation.mutate(cluster.id)}
            />
          ))}
        </div>
      </Drawer>

      <Modal
        title="拆分观点簇"
        open={Boolean(splitTarget)}
        okText="确认拆分"
        cancelText="取消"
        confirmLoading={splitMutation.isPending}
        okButtonProps={{ disabled: !splitName.trim() || splitClaimIds.length === 0 }}
        onCancel={() => setSplitTarget(null)}
        onOk={() => splitMutation.mutate()}
      >
        <p>选择要移动到新观点簇的观点。原簇和来源记录都会保留。</p>
        <Input
          value={splitName}
          placeholder="新观点簇名称"
          onChange={(event) => setSplitName(event.target.value)}
        />
        <Checkbox.Group
          className="cluster-claim-options"
          value={splitClaimIds}
          onChange={(values) => setSplitClaimIds(values.map(String))}
          options={(splitTarget?.claim_ids ?? []).map((claimId, index) => ({
            label: `观点 ${index + 1} · ${claimId.slice(0, 8)}`,
            value: claimId,
          }))}
        />
      </Modal>
    </div>
  );
}
