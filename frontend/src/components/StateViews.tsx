import {
  CloudServerOutlined,
  InboxOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Alert, Button, Empty, Skeleton } from "antd";
import type { ReactNode } from "react";

export function LoadingBlock({ rows = 7 }: { rows?: number }) {
  return (
    <div className="state-block" aria-label="正在加载">
      <Skeleton active paragraph={{ rows }} title={false} />
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-block">
      <Empty
        image={<InboxOutlined className="empty-state__icon" />}
        description={
          <div>
            <strong>{title}</strong>
            <p>{description}</p>
          </div>
        }
      >
        {action}
      </Empty>
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const message = error instanceof Error ? error.message : "暂时无法读取数据";
  return (
    <Alert
      className="state-block"
      type="error"
      showIcon
      icon={<CloudServerOutlined />}
      title="数据加载失败"
      description={`原因：${message}。当前页面数据可能不完整，请检查后端和 Redis 后重试。`}
      action={
        onRetry && (
          <Button icon={<ReloadOutlined />} onClick={onRetry}>
            重新加载
          </Button>
        )
      }
    />
  );
}
