import {
  CheckCircleFilled,
  ClockCircleFilled,
  CloseCircleFilled,
  MinusCircleFilled,
  PauseCircleFilled,
  SyncOutlined,
} from "@ant-design/icons";
import { Tag } from "antd";
import type { ReactNode } from "react";

const statusMap: Record<
  string,
  { label: string; color: string; icon: ReactNode }
> = {
  candidate: { label: "待处理", color: "default", icon: <ClockCircleFilled /> },
  pending: { label: "等待手动执行", color: "default", icon: <ClockCircleFilled /> },
  disabled: { label: "等待手动执行", color: "default", icon: <ClockCircleFilled /> },
  paused: { label: "已暂停", color: "warning", icon: <PauseCircleFilled /> },
  image_result_unknown: { label: "生图结果待核对", color: "warning", icon: <PauseCircleFilled /> },
  generating_image: { label: "Codex 生图", color: "processing", icon: <SyncOutlined spin /> },
  rendering_image: { label: "排版渲染", color: "processing", icon: <SyncOutlined spin /> },
  running: { label: "执行中", color: "processing", icon: <SyncOutlined spin /> },
  completed: { label: "已完成", color: "success", icon: <CheckCircleFilled /> },
  insufficient_candidates: { label: "候选题不足", color: "warning", icon: <PauseCircleFilled /> },
  queued: { label: "队列中", color: "processing", icon: <ClockCircleFilled /> },
  preparing_input: { label: "准备输入", color: "processing", icon: <SyncOutlined spin /> },
  fetching_question: { label: "读取问题", color: "processing", icon: <SyncOutlined spin /> },
  fetching_answers: { label: "采集回答", color: "processing", icon: <SyncOutlined spin /> },
  cleaning_answers: { label: "清洗去重", color: "processing", icon: <SyncOutlined spin /> },
  evaluating_answers: { label: "质量筛选", color: "processing", icon: <SyncOutlined spin /> },
  extracting_claims: { label: "观点提取", color: "processing", icon: <SyncOutlined spin /> },
  generating_embeddings: { label: "生成向量", color: "processing", icon: <SyncOutlined spin /> },
  clustering_claims: { label: "观点粗聚类", color: "processing", icon: <SyncOutlined spin /> },
  refining_clusters: { label: "聚类修正", color: "processing", icon: <SyncOutlined spin /> },
  generating_opinion_map: { label: "观点地图", color: "processing", icon: <SyncOutlined spin /> },
  generating_article: { label: "生成文章", color: "processing", icon: <SyncOutlined spin /> },
  reviewing_article: { label: "独立审核", color: "processing", icon: <SyncOutlined spin /> },
  saving_result: { label: "保存结果", color: "processing", icon: <SyncOutlined spin /> },
  waiting_review: { label: "待审核", color: "warning", icon: <ClockCircleFilled /> },
  waiting_browser: { label: "等待 Chrome 扩展", color: "warning", icon: <PauseCircleFilled /> },
  waiting_login: { label: "等待知乎登录", color: "warning", icon: <PauseCircleFilled /> },
  waiting_verification: { label: "等待人工验证", color: "warning", icon: <PauseCircleFilled /> },
  review_rejected: { label: "已退回", color: "error", icon: <CloseCircleFilled /> },
  review_approved: { label: "已通过", color: "success", icon: <CheckCircleFilled /> },
  scheduled: { label: "已排期", color: "cyan", icon: <ClockCircleFilled /> },
  published: { label: "已发布", color: "success", icon: <CheckCircleFilled /> },
  failed: { label: "失败", color: "error", icon: <CloseCircleFilled /> },
  cancelled: { label: "已取消", color: "default", icon: <PauseCircleFilled /> },
  ignored: { label: "已忽略", color: "default", icon: <MinusCircleFilled /> },
};

export function statusLabel(status: string) {
  return statusMap[status]?.label ?? status;
}

export function StatusTag({ status }: { status: string }) {
  const value = statusMap[status] ?? {
    label: status,
    color: "default",
    icon: <ClockCircleFilled />,
  };
  return (
    <Tag className="status-tag" color={value.color} icon={value.icon}>
      {value.label}
    </Tag>
  );
}
