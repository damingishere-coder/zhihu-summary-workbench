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
  queued: { label: "队列中", color: "processing", icon: <ClockCircleFilled /> },
  preparing_input: { label: "准备输入", color: "processing", icon: <SyncOutlined spin /> },
  extracting_claims: { label: "观点提取", color: "processing", icon: <SyncOutlined spin /> },
  saving_result: { label: "保存结果", color: "processing", icon: <SyncOutlined spin /> },
  waiting_review: { label: "待审核", color: "warning", icon: <ClockCircleFilled /> },
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

