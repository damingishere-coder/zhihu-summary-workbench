import type { Task } from "../types";

export const runningStatuses = [
  "queued",
  "preparing_input",
  "saving_result",
  "fetching_question",
  "fetching_answers",
  "cleaning_answers",
  "evaluating_answers",
  "extracting_claims",
  "generating_embeddings",
  "clustering_claims",
  "refining_clusters",
  "generating_opinion_map",
  "generating_article",
  "reviewing_article",
  "generating_image",
  "rendering_image",
  "rendering_infographic",
];
export const attentionStatuses = [
  "paused",
  "failed",
  "waiting_browser",
  "waiting_login",
  "waiting_verification",
  "image_result_unknown",
];

export function taskAction(
  task: Pick<
    Task,
    "id" | "question_id" | "status" | "error_message" | "result"
  >,
) {
  const detail = `/questions/${task.question_id}`;
  const browser = `/settings/browser?taskId=${encodeURIComponent(task.id)}&returnTo=${encodeURIComponent(detail)}`;
  if (task.status === "waiting_login")
    return { label: "处理知乎登录", href: browser };
  if (task.status === "waiting_verification")
    return { label: "处理人工验证", href: browser };
  if (task.status === "waiting_browser")
    return { label: "连接浏览器扩展", href: browser };
  if (task.status === "image_result_unknown")
    return { label: "核对已有图片", href: detail };
  if (task.error_message?.startsWith("资料不足"))
    return { label: "检查资料并继续", href: detail };
  if (task.status === "waiting_review" && task.result.draft_id)
    return {
      label: "检查作品",
      href: `/drafts/${task.result.draft_id}/review`,
    };
  if (task.status === "failed")
    return { label: "查看原因并处理", href: detail };
  if (task.status === "paused") return { label: "查看并继续", href: detail };
  return { label: "查看进度", href: detail };
}
