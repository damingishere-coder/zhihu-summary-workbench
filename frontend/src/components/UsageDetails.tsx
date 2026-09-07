import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Collapse, Descriptions } from "antd";
import { api } from "../api/client";
import { ErrorState, LoadingBlock } from "./StateViews";

export function UsageDetails() {
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: ["model-usage"],
    queryFn: api.modelUsage,
    enabled: open,
  });
  return (
    <Collapse
      ghost
      className="system-details"
      onChange={(keys) => setOpen(keys.length > 0)}
      items={[
        {
          key: "usage",
          label: "今日模型用量与费用",
          children: (
            <>
              {query.isLoading && <LoadingBlock rows={2} />}
              {query.isError && (
                <ErrorState
                  error={query.error}
                  onRetry={() => void query.refetch()}
                />
              )}
              {query.data && (
                <Descriptions
                  column={{ xs: 1, md: 2 }}
                  items={[
                    {
                      key: "calls",
                      label: "模型调用",
                      children: `${query.data.calls} 次`,
                    },
                    {
                      key: "cost",
                      label: "估算费用",
                      children:
                        query.data.cost_known === false
                          ? "未知（Codex 额度）"
                          : `¥${query.data.estimated_cost.toFixed(4)}`,
                    },
                    {
                      key: "tokens",
                      label: "Token",
                      children:
                        query.data.usage_known === false
                          ? "用量未报告"
                          : `${query.data.input_tokens} 输入 / ${query.data.output_tokens} 输出`,
                    },
                    {
                      key: "manual",
                      label: "手动图片提示词",
                      children: `${query.data.manual_image_generations} 次`,
                    },
                  ]}
                />
              )}
            </>
          ),
        },
      ]}
    />
  );
}
