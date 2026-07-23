import {
  ArrowLeftOutlined,
  FileTextOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Descriptions,
  Divider,
  Progress,
  Space,
  Timeline,
  Typography,
} from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { PriorityTag } from "../components/PriorityTag";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import { formatDateTime } from "../utils/format";

export function QuestionDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const questionQuery = useQuery({
    queryKey: ["questions", id],
    queryFn: () => api.question(id),
    enabled: Boolean(id),
  });
  const taskId = questionQuery.data?.latest_task_id;
  const taskQuery = useQuery({
    queryKey: ["tasks", taskId],
    queryFn: () => api.task(taskId!),
    enabled: Boolean(taskId),
    refetchInterval: (query) =>
      ["queued", "extracting_claims"].includes(query.state.data?.status ?? "") ? 2_000 : false,
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["questions"] });
    await queryClient.invalidateQueries({ queryKey: ["tasks"] });
    await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const queueMutation = useMutation({
    mutationFn: () => api.queueQuestion(id),
    onSuccess: async () => {
      message.success("任务已加入队列");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });
  const retryMutation = useMutation({
    mutationFn: (task: string) => api.retryTask(task),
    onSuccess: async () => {
      message.success("任务已重新入队");
      await refresh();
    },
    onError: (error) => message.error(error.message),
  });

  if (questionQuery.isLoading) return <div className="page"><LoadingBlock rows={14} /></div>;
  if (questionQuery.isError) {
    return <div className="page"><ErrorState error={questionQuery.error} onRetry={() => void questionQuery.refetch()} /></div>;
  }
  const question = questionQuery.data;
  if (!question) return null;
  const task = taskQuery.data;
  const analysis = task?.result.analysis;

  return (
    <div className="page">
      <Button className="back-button" type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/questions")}>
        返回问题池
      </Button>
      <PageHeader
        eyebrow={`问题 ID · ${question.external_id ?? question.id.slice(0, 8)}`}
        title={question.title}
        description="查看问题来源、第一阶段结构化分析、任务进度和日志。"
        actions={
          <Space>
            <Button icon={<LinkOutlined />} href={question.url} target="_blank" rel="noreferrer">
              打开原问题
            </Button>
            {!task || ["failed", "cancelled"].includes(task.status) ? (
              task && ["failed", "cancelled"].includes(task.status) ? (
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  loading={retryMutation.isPending}
                  onClick={() => retryMutation.mutate(task.id)}
                >
                  重试任务
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={queueMutation.isPending}
                  onClick={() => queueMutation.mutate()}
                >
                  加入任务
                </Button>
              )
            ) : null}
          </Space>
        }
      />
      <div className="detail-grid">
        <main className="detail-main">
          <section className="work-surface detail-section">
            <div className="section-heading">
              <h2>问题信息</h2>
              <Space><PriorityTag priority={question.priority} /><StatusTag status={question.status} /></Space>
            </div>
            <Descriptions column={{ xs: 1, md: 2 }} size="small">
              <Descriptions.Item label="来源">
                {{ manual: "手动推荐", import: "批量导入", hot: "热门问题" }[question.source] || question.source}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(question.created_at, true)}</Descriptions.Item>
              <Descriptions.Item label="问题链接" span="filled">
                <Typography.Link href={question.url} target="_blank" ellipsis>{question.url}</Typography.Link>
              </Descriptions.Item>
            </Descriptions>
            <Divider />
            <h3>问题说明</h3>
            <p className="long-copy">{question.description || "未填写问题说明。"}</p>
            <h3>示例回答</h3>
            <p className="sample-answer">{question.sample_answer || "未填写示例回答，Worker 将使用问题说明或标题验证流程。"}</p>
          </section>

          <section className="work-surface detail-section">
            <div className="section-heading">
              <h2>原始回答</h2>
              <StatusTag status="candidate" />
            </div>
            <Alert
              type="info"
              showIcon
              title="第一阶段边界"
              description="真实知乎回答采集、清洗和去重将在第二阶段实现。当前示例回答只用于验证 Provider、Worker、SSE 和结构化结果保存。"
            />
          </section>

          <section className="work-surface detail-section">
            <div className="section-heading">
              <h2>结构化观点结果</h2>
              {analysis && <Button icon={<FileTextOutlined />} onClick={() => navigate(`/drafts/${task?.result.draft_id}/review`)}>打开最小草稿</Button>}
            </div>
            {!analysis ? (
              <p className="section-empty">任务完成后，这里会展示经过 Pydantic 校验的摘要、观点、理由和风险。</p>
            ) : (
              <div className="analysis-grid">
                <div className="analysis-summary">
                  <span>摘要</span>
                  <strong>{analysis.summary}</strong>
                </div>
                <div>
                  <h3>核心观点</h3>
                  <ol>{analysis.core_claims.map((item) => <li key={item}>{item}</li>)}</ol>
                </div>
                <div>
                  <h3>支持理由</h3>
                  <ul>{analysis.supporting_reasons.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
                <div>
                  <h3>风险与限制</h3>
                  <ul>{analysis.risks_or_limitations.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
                <div className="score-row">
                  <span>质量分 <strong>{analysis.quality_score}</strong></span>
                  <span>相关性 <strong>{analysis.relevance_score}</strong></span>
                  <span>立场 <strong>{analysis.position}</strong></span>
                </div>
              </div>
            )}
          </section>
        </main>
        <aside className="detail-aside">
          <section className="work-surface detail-section detail-section--sticky">
            <div className="section-heading">
              <h2>任务进度</h2>
              {task && <StatusTag status={task.status} />}
            </div>
            {taskQuery.isLoading && <LoadingBlock rows={5} />}
            {!taskId && <p className="section-empty">尚未创建任务。</p>}
            {task && (
              <>
                <Progress percent={task.progress} status={task.status === "failed" ? "exception" : task.progress === 100 ? "success" : "active"} />
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="当前阶段"><StatusTag status={task.stage} /></Descriptions.Item>
                  <Descriptions.Item label="Worker">{task.worker_id || "等待分配"}</Descriptions.Item>
                  <Descriptions.Item label="重试次数">{task.retry_count} / {task.max_retries}</Descriptions.Item>
                  <Descriptions.Item label="模型">{task.result.model || "等待调用"}</Descriptions.Item>
                </Descriptions>
                {task.error_message && <Alert type="error" showIcon title={task.error_message} />}
                <Divider />
                <h3>任务日志</h3>
                <Timeline
                  items={(task.logs ?? []).map((log) => ({
                    color: log.level === "error" ? "red" : log.level === "warning" ? "orange" : "blue",
                    content: (
                      <div className="task-log-item">
                        <time>{formatDateTime(log.created_at)}</time>
                        <p>{log.message}</p>
                      </div>
                    ),
                  }))}
                />
              </>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
