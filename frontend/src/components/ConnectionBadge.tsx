import {
  CheckCircleFilled,
  LoadingOutlined,
  WarningFilled,
} from "@ant-design/icons";
import type { ConnectionState } from "../api/events";

export function ConnectionBadge({ state }: { state: ConnectionState }) {
  if (state === "connected") {
    return (
      <span className="connection-badge connection-badge--ok">
        <CheckCircleFilled /> 实时更新
      </span>
    );
  }
  if (state === "reconnecting") {
    return (
      <span className="connection-badge connection-badge--warning">
        <WarningFilled /> 正在重连
      </span>
    );
  }
  return (
    <span className="connection-badge">
      <LoadingOutlined /> 正在连接
    </span>
  );
}

