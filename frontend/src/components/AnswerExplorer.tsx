import {
  CheckCircleOutlined,
  CommentOutlined,
  LinkOutlined,
  LikeOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Button, Collapse, Empty, Space, Tag, Tooltip, Typography } from "antd";
import type { AnswerList } from "../types";

export function AnswerExplorer({
  data,
  pendingId,
  onToggle,
}: {
  data: AnswerList | undefined;
  pendingId?: string;
  onToggle: (answerId: string, included: boolean) => void;
}) {
  if (!data?.items.length) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="任务采集回答后会显示在这里"
      />
    );
  }

  return (
    <div className="answer-explorer">
      <div className="answer-summary-strip">
        <span>已采集 <strong>{data.total}</strong></span>
        <span className="answer-summary-strip__included">
          纳入 <strong>{data.included}</strong>
        </span>
        <span>过滤 <strong>{data.filtered}</strong></span>
      </div>
      <Collapse
        ghost
        className="answer-list"
        items={data.items.map((answer) => ({
          key: answer.id,
          label: (
            <div className="answer-row-heading">
              <div>
                <strong>{answer.author_name || "匿名用户"}</strong>
                <Space size={10}>
                  <span><LikeOutlined /> {answer.vote_count}</span>
                  <span><CommentOutlined /> {answer.comment_count}</span>
                </Space>
              </div>
              <Tag color={answer.included_for_analysis ? "success" : "default"}>
                {answer.included_for_analysis ? "已纳入" : "已过滤"}
              </Tag>
            </div>
          ),
          extra: (
            <Tooltip
              title={answer.included_for_analysis ? "从后续分析中排除" : "强制纳入后续分析"}
            >
              <Button
                type="text"
                size="small"
                aria-label={answer.included_for_analysis ? "排除回答" : "纳入回答"}
                icon={answer.included_for_analysis ? <StopOutlined /> : <CheckCircleOutlined />}
                loading={pendingId === answer.id}
                onClick={(event) => {
                  event.stopPropagation();
                  onToggle(answer.id, !answer.included_for_analysis);
                }}
              />
            </Tooltip>
          ),
          children: (
            <div className="answer-detail">
              {answer.filter_reason && (
                <p className="answer-filter-reason">过滤原因：{answer.filter_reason}</p>
              )}
              {answer.analysis && (
                <div className="answer-scores">
                  <span>质量 {answer.analysis.quality_score ?? "—"}</span>
                  <span>相关 {answer.analysis.relevance_score ?? "—"}</span>
                  <span>密度 {answer.analysis.information_density ?? "—"}</span>
                </div>
              )}
              <Typography.Paragraph className="answer-copy">
                {answer.plain_content}
              </Typography.Paragraph>
              <Button
                type="link"
                size="small"
                icon={<LinkOutlined />}
                href={answer.answer_url}
                target="_blank"
                rel="noreferrer"
              >
                打开原回答
              </Button>
            </div>
          ),
        }))}
      />
    </div>
  );
}
