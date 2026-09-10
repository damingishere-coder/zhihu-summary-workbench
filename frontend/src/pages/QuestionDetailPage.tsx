import {
  ArrowLeftOutlined,
  ApiOutlined,
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
  Drawer,
  Tabs,
  Pagination,
  Progress,
  Space,
  Timeline,
} from "antd";
import { useState } from "react";
import { useListLocation } from "../hooks/useListLocation";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { AnswerExplorer } from "../components/AnswerExplorer";
import { OpinionMapPanel } from "../components/OpinionMapPanel";
import { PageHeader } from "../components/PageHeader";
import { runningStatuses } from "../utils/taskActions";
import { PriorityTag } from "../components/PriorityTag";
import { ErrorState, LoadingBlock } from "../components/StateViews";
import { StatusTag } from "../components/StatusTag";
import { formatDateTime } from "../utils/format";

const processingStates = runningStatuses;

function captureMethodLabel(value: string | null | undefined) {
  return (
    {
      rendered_dom: "当前页面 DOM",
      same_origin_api: "显式同源 API",
      json_import: "人工 JSON 导入",
    }[value ?? ""] ??
    value ??
    "等待采集"
  );
}

function recoveryActionLabel(value: string | undefined) {
  return (
    {
      login: "在当前标签页登录后重试",
      complete_verification: "完成人工验证后重试",
      retry_visible_page_or_import_json:
        "重新打开正常问题页采集，仍失败时导入 JSON",
    }[value ?? ""] ?? ""
  );
}

export function QuestionDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const list = useListLocation();
  const tab = list.get("tab", "overview");
  const [detailsOpen, setDetailsOpen] = useState(false);
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
      processingStates.includes(query.state.data?.status ?? "") ? 2_000 : false,
  });
  const answersQuery = useQuery({
    queryKey: ["answers", id, list.page],
    queryFn: () => api.answers(id, { limit: 50, offset: (list.page - 1) * 50 }),
    enabled: Boolean(id),
    refetchInterval: processingStates.includes(taskQuery.data?.status ?? "")
      ? 3_000
      : false,
  });
  const analysisQuery = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => api.analysis(id),
    enabled: Boolean(id),
    refetchInterval: processingStates.includes(taskQuery.data?.status ?? "")
      ? 3_000
      : false,
  });
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["questions"] }),
      queryClient.invalidateQueries({ queryKey: ["tasks"] }),
      queryClient.invalidateQueries({ queryKey: ["answers", id] }),
      queryClient.invalidateQueries({ queryKey: ["analysis", id] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  };
  const queueMutation = useMutation({
    mutationFn: () => api.queueQuestion(id),
    onSuccess: async () => {
      message.success("完整内容任务已加入队列");
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
  const continueMutation = useMutation({
    mutationFn: (taskId: string) =>
      taskQuery.data?.error_message?.startsWith("资料不足")
        ? api.continuePartialTask(taskId)
        : api.continueTask(taskId),
    onSuccess: refresh,
    onError: (error) => message.error(error.message),
  });
  const answerToggle = useMutation({
    mutationFn: ({
      answerId,
      included,
    }: {
      answerId: string;
      included: boolean;
    }) =>
      included ? api.includeAnswer(answerId) : api.excludeAnswer(answerId),
    onSuccess: async () => {
      message.success("回答分析状态已更新；重跑分析时会使用新选择");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["answers", id] }),
        queryClient.invalidateQueries({ queryKey: ["analysis", id] }),
      ]);
    },
    onError: (error) => message.error(error.message),
  });

  if (questionQuery.isLoading) {
    return (
      <div className="page">
        <LoadingBlock rows={16} />
      </div>
    );
  }
  if (questionQuery.isError) {
    return (
      <div className="page">
        <ErrorState
          error={questionQuery.error}
          onRetry={() => void questionQuery.refetch()}
        />
      </div>
    );
  }
  const question = questionQuery.data;
  if (!question) return null;
  const task = taskQuery.data;
  const analysis = analysisQuery.data;
  const draftId = analysis?.latest_draft_id ?? question.latest_draft_id;
  const waitingForLogin = task?.status === "waiting_login";
  const waitingForVerification = task?.status === "waiting_verification";
  const waitingForBrowser = task?.status === "waiting_browser";

  return (
    <div className="page">
      <Button
        className="back-button"
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() =>
          navigate(
            list.get("returnTo").startsWith("/questions?")
              ? list.get("returnTo")
              : "/questions",
          )
        }
      >
        返回选题
      </Button>
      <PageHeader
        eyebrow={`问题 ID · ${question.external_id ?? question.id.slice(0, 8)}`}
        title={question.title}
        description="了解采集范围，检查回答与观点，再进入作品。"
        actions={
          <Space wrap>
            <Button onClick={() => setDetailsOpen(true)}>任务详情与费用</Button>
            <Button
              icon={<LinkOutlined />}
              href={question.url}
              target="_blank"
              rel="noreferrer"
            >
              打开原问题
            </Button>
            {draftId && (
              <Button
                icon={<FileTextOutlined />}
                onClick={() => navigate(`/drafts/${draftId}/review`)}
              >
                打开草稿审核
              </Button>
            )}
            {!task ? (
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={queueMutation.isPending}
                onClick={() => queueMutation.mutate()}
              >
                开始完整分析
              </Button>
            ) : ["paused", "image_result_unknown"].includes(task.status) ? (
              <Button
                type="primary"
                loading={continueMutation.isPending}
                onClick={() => continueMutation.mutate(task.id)}
              >
                {task.error_message?.startsWith("资料不足")
                  ? "按现有资料继续"
                  : task.status === "image_result_unknown"
                    ? "核对已有图片并继续"
                    : "继续任务"}
              </Button>
            ) : ["failed", "cancelled"].includes(task.status) ? (
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                loading={retryMutation.isPending}
                onClick={() => retryMutation.mutate(task.id)}
              >
                重试任务
              </Button>
            ) : null}
          </Space>
        }
      />

      <Tabs
        activeKey={
          ["overview", "answers", "opinions"].includes(tab) ? tab : "overview"
        }
        onChange={(value) => list.set("tab", value)}
        items={[
          { key: "overview", label: "概览" },
          { key: "answers", label: "回答" },
          { key: "opinions", label: "观点地图" },
        ]}
      />
      <div hidden={tab !== "overview" && ["answers", "opinions"].includes(tab)}>
        <section className="work-surface question-context-strip">
          <Descriptions column={{ xs: 1, md: 3, xl: 6 }} size="small">
            <Descriptions.Item label="状态">
              <StatusTag status={question.status} />
            </Descriptions.Item>
            <Descriptions.Item label="优先级">
              <PriorityTag priority={question.priority} />
            </Descriptions.Item>
            <Descriptions.Item label="来源">
              {{ manual: "手动推荐", import: "批量导入", hot: "知乎热榜" }[
                question.source
              ] ?? question.source}
            </Descriptions.Item>
            <Descriptions.Item label="平台回答数">
              {question.answer_count || "—"}
            </Descriptions.Item>
            <Descriptions.Item label="关注数">
              {question.follower_count || "—"}
            </Descriptions.Item>
            <Descriptions.Item label="最近采集">
              {question.fetched_at
                ? formatDateTime(question.fetched_at, true)
                : "尚未采集"}
            </Descriptions.Item>
          </Descriptions>
        </section>

        {waitingForLogin && task && (
          <Alert
            className="phase-alert"
            type="warning"
            showIcon
            title="任务正在等待知乎登录"
            description={
              task.error_message ??
              "请在正常 Chrome 知乎标签页完成登录后继续任务。"
            }
            action={
              <Button
                type="primary"
                icon={<ApiOutlined />}
                onClick={() =>
                  navigate(
                    `/settings/browser?taskId=${encodeURIComponent(task.id)}&returnTo=${encodeURIComponent(`/questions/${id}`)}`,
                  )
                }
              >
                打开 Chrome 扩展设置
              </Button>
            }
          />
        )}
        {waitingForVerification && task && (
          <Alert
            className="phase-alert"
            type="warning"
            showIcon
            title="任务正在等待人工验证"
            description={`这表示知乎在正常 Chrome 标签页中要求人工处理，不代表账号已经退出。请在同一个知乎标签页完成验证，再让扩展重新采集。${
              task.error_message ? ` 本次记录：${task.error_message}` : ""
            }`}
            action={
              <Button
                type="primary"
                icon={<ApiOutlined />}
                onClick={() =>
                  navigate(
                    `/settings/browser?taskId=${encodeURIComponent(task.id)}&returnTo=${encodeURIComponent(`/questions/${id}`)}`,
                  )
                }
              >
                打开扩展设置并继续
              </Button>
            }
          />
        )}
        {waitingForBrowser && task && (
          <Alert
            className="phase-alert"
            type="info"
            showIcon
            title="任务正在等待 Chrome 扩展"
            description={
              task.error_message ??
              "Worker 已释放；扩展回传回答后任务会自动重新入队。"
            }
            action={
              <Button
                type="primary"
                icon={<ApiOutlined />}
                onClick={() =>
                  navigate(
                    `/settings/browser?taskId=${encodeURIComponent(task.id)}&returnTo=${encodeURIComponent(`/questions/${id}`)}`,
                  )
                }
              >
                连接扩展或导入 JSON
              </Button>
            }
          />
        )}
        {task?.error_message &&
          !waitingForLogin &&
          !waitingForVerification &&
          !waitingForBrowser && (
            <Alert
              className="phase-alert"
              type="error"
              showIcon
              title="任务需要处理"
              description={`原因：${task.error_message}。已采集和已生成的数据会保留，请按上方提示处理后继续。`}
            />
          )}
        {task?.result.warnings?.map((warning) => (
          <Alert
            key={warning}
            className="phase-alert"
            type="warning"
            showIcon
            title={warning}
          />
        ))}
        {task?.result.capture?.diagnostics
          ?.filter((item) => item.level !== "info" && !(task.result.capture?.stop_reason === "no_progress" && item.code === "answer_limit_not_reached"))
          .map((item) => (
            <Alert
              key={`${item.code}-${item.message}`}
              className="phase-alert"
              type={item.level === "error" ? "error" : "warning"}
              showIcon
              title={item.message}
            />
          ))}

        <section className="work-surface question-overview">
          <h2>这道题进行到哪一步了？</h2>
          {task ? (
            <>
              <StatusTag status={task.status} />
              <Progress percent={task.progress} />
              <p>
                已保存{" "}
                {answersQuery.data?.total ??
                  task.result.capture?.collected_answer_count ??
                  "未知数量的"}{" "}
                条回答。
                {typeof task.result.capture?.collected_answer_count === "number" &&
                  answersQuery.data?.total !== undefined &&
                  answersQuery.data.total !== task.result.capture.collected_answer_count &&
                  `本次刷新读取 ${task.result.capture.collected_answer_count} 条，其余为此前已保存资料。`}
                {task.result.capture?.stop_reason === "no_progress"
                  ? "连续回滑未出现新回答，已按本次可获取的最多回答完成采集。平台标注数量可能仍有差额。"
                  : "仅代表当前已保存的资料，不等于读取全部回答。"}
              </p>
            </>
          ) : (
            <p>还没有开始生成。准备好后，点击上方“开始完整分析”。</p>
          )}
          <Space wrap>
            <Button onClick={() => list.set("tab", "answers")}>
              检查原始回答
            </Button>
            <Button onClick={() => list.set("tab", "opinions")}>
              查看观点地图
            </Button>
            {draftId && (
              <Button
                type="primary"
                onClick={() => navigate(`/drafts/${draftId}/review`)}
              >
                检查作品
              </Button>
            )}
          </Space>
        </section>
      </div>
      <div className="question-panels">
        <section
          className="work-surface question-analysis-column"
          hidden={tab !== "answers"}
        >
          <div className="section-heading">
            <div>
              <h2>原始回答</h2>
              <p>展开查看正文、质量评分和原回答。</p>
            </div>
          </div>
          {answersQuery.isLoading ? (
            <LoadingBlock rows={12} />
          ) : answersQuery.isError ? (
            <ErrorState
              error={answersQuery.error}
              onRetry={() => void answersQuery.refetch()}
            />
          ) : (
            <>
              <AnswerExplorer
                data={answersQuery.data}
                pendingId={answerToggle.variables?.answerId}
                onToggle={(answerId, included) =>
                  answerToggle.mutate({ answerId, included })
                }
              />
              <Pagination
                current={list.page}
                pageSize={50}
                total={answersQuery.data?.total ?? 0}
                showSizeChanger={false}
                hideOnSinglePage
                showTotal={(total, range) => `第 ${range[0]}–${range[1]} 条，共 ${total} 条回答`}
                onChange={(page) => list.set("page", page)}
              />
            </>
          )}
        </section>

        <section
          className="work-surface question-analysis-column"
          hidden={tab !== "opinions"}
        >
          <div className="section-heading">
            <div>
              <h2>观点地图</h2>
              <p>共识、分歧、少数派和适用条件。</p>
            </div>
            {analysis?.opinion_map_version && (
              <span className="section-caption">
                v{analysis.opinion_map_version}
              </span>
            )}
          </div>
          {analysisQuery.isLoading ? (
            <LoadingBlock rows={12} />
          ) : analysisQuery.isError ? (
            <ErrorState
              error={analysisQuery.error}
              onRetry={() => void analysisQuery.refetch()}
            />
          ) : (
            <OpinionMapPanel
              analysis={analysis}
              onChanged={async () => {
                await Promise.all([
                  queryClient.invalidateQueries({ queryKey: ["analysis", id] }),
                  queryClient.invalidateQueries({ queryKey: ["tasks"] }),
                ]);
              }}
            />
          )}
        </section>

        <Drawer
          title="任务详情与费用"
          open={detailsOpen}
          onClose={() => setDetailsOpen(false)}
          size="min(600px, 94vw)"
        >
          <aside className="question-analysis-column question-analysis-column--rail">
            <div className="section-heading">
              <h2>任务、模型与费用</h2>
              {task && <StatusTag status={task.status} />}
            </div>
            {!task ? (
              <p className="section-empty">
                尚未创建任务。点击“开始完整分析”后可查看实时阶段。
              </p>
            ) : (
              <>
                <Progress
                  percent={task.progress}
                  status={
                    task.status === "failed"
                      ? "exception"
                      : task.progress === 100
                        ? "success"
                        : "active"
                  }
                />
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="当前阶段">
                    <StatusTag status={task.stage} />
                  </Descriptions.Item>
                  <Descriptions.Item label="Worker">
                    {task.worker_id || "等待分配"}
                  </Descriptions.Item>
                  <Descriptions.Item label="重试次数">
                    {task.retry_count} / {task.max_retries}
                  </Descriptions.Item>
                  <Descriptions.Item label="采集方式">
                    {task.result.capture?.method
                      ? captureMethodLabel(task.result.capture.method)
                      : task.result.collector_mode || "等待采集"}
                  </Descriptions.Item>
                  <Descriptions.Item label="回答数量">
                    {task.result.capture?.collected_answer_count ?? "—"} / 可见{" "}
                    {task.result.capture?.visible_answer_count ?? "—"}
                  </Descriptions.Item>
                  {task.result.capture?.page_url && (
                    <Descriptions.Item label="采集页面">
                      <a
                        href={task.result.capture.page_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        打开知乎问题页
                      </a>
                    </Descriptions.Item>
                  )}
                  {task.result.capture?.recommended_action && (
                    <Descriptions.Item label="建议恢复">
                      {recoveryActionLabel(
                        task.result.capture.recommended_action,
                      )}
                    </Descriptions.Item>
                  )}
                  <Descriptions.Item label="模型调用">
                    {analysis?.model_usage.calls ?? 0} 次
                  </Descriptions.Item>
                  <Descriptions.Item label="Token">
                    {(analysis?.model_usage.input_tokens ?? 0).toLocaleString()}{" "}
                    输入 /{" "}
                    {(
                      analysis?.model_usage.output_tokens ?? 0
                    ).toLocaleString()}{" "}
                    输出
                  </Descriptions.Item>
                  <Descriptions.Item label="估算费用">
                    ¥{(analysis?.model_usage.estimated_cost ?? 0).toFixed(4)}
                  </Descriptions.Item>
                </Descriptions>
                <h3>任务日志</h3>
                <Timeline
                  items={(task.logs ?? []).map((log) => ({
                    color:
                      log.level === "error"
                        ? "red"
                        : log.level === "warning"
                          ? "orange"
                          : "blue",
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
          </aside>
        </Drawer>
      </div>
    </div>
  );
}
