import { Tag } from "antd";
import type { Priority } from "../types";

const map: Record<Priority, { label: string; color: string }> = {
  high: { label: "高", color: "red" },
  medium: { label: "中", color: "orange" },
  low: { label: "低", color: "green" },
};

export function PriorityTag({ priority }: { priority: Priority }) {
  const value = map[priority];
  return <Tag color={value.color}>{value.label}</Tag>;
}

