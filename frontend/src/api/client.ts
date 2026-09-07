import type {
  DashboardSummary,
  AnswerList,
  AnalysisOverview,
  ClaimCluster,
  Draft,
  DraftVersion,
  InfographicContent,
  ImageWorkspace,
  ImportResult,
  ModelTestResult,
  Paginated,
  PublicSettings,
  PublishReadiness,
  PublishRecord,
  PublishSchedule,
  DailyPlan,
  ModelUsageOverview,
  PromptTemplate,
  PromptVersion,
  BrowserSafetyState,
  ManagedBrowserSession,
  BrowserBridgeStatus,
  BridgePairing,
  ImportBundleV1,
  OpenSourceReference,
  Question,
  Task,
  Worker,
} from "../types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = (await response.json()) as { detail?: string | Array<{ msg: string }> };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (Array.isArray(payload.detail)) {
        message = payload.detail.map((item) => item.msg).join("；");
      }
    } catch {
      // 服务端没有返回 JSON 时保留可理解的状态码消息。
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function queryString(values: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  dashboard: () => request<DashboardSummary>("/dashboard/summary"),

  questions: (filters: Record<string, string | number | undefined> = {}) =>
    request<Paginated<Question>>(`/questions${queryString(filters)}`),
  question: (id: string) => request<Question>(`/questions/${id}`),
  answers: (id: string, filters: Record<string, string | number | undefined> = {}) =>
    request<AnswerList>(`/questions/${id}/answers${queryString(filters)}`),
  analysis: (id: string) => request<AnalysisOverview>(`/questions/${id}/analysis`),
  includeAnswer: (id: string) =>
    request(`/answers/${id}/include`, { method: "POST" }),
  excludeAnswer: (id: string) =>
    request(`/answers/${id}/exclude`, { method: "POST" }),
  addQuestion: (payload: {
    url: string;
    title?: string;
    description?: string;
    sample_answer?: string;
    priority: string;
  }) =>
    request<Question>("/questions/manual", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importQuestions: (payload: { urls: string[]; priority: string }) =>
    request<ImportResult>("/questions/import", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateQuestion: (id: string, payload: Partial<Question>) =>
    request<Question>(`/questions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  queueQuestion: (id: string) =>
    request<Task>(`/questions/${id}/queue`, { method: "POST" }),
  ignoreQuestion: (id: string) =>
    request<Question>(`/questions/${id}/ignore`, { method: "POST" }),
  deleteQuestion: (id: string) =>
    request<void>(`/questions/${id}`, { method: "DELETE" }),
  updateCluster: (
    id: string,
    payload: Partial<
      Pick<
        ClaimCluster,
        | "name"
        | "summary"
        | "cluster_type"
        | "is_mainstream"
        | "is_minority"
        | "is_controversial"
        | "sort_order"
        | "write_policy"
      >
    >,
  ) =>
    request<ClaimCluster>(`/clusters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  mergeClusters: (clusterIds: string[], name?: string) =>
    request<ClaimCluster>("/clusters/merge", {
      method: "POST",
      body: JSON.stringify({ cluster_ids: clusterIds, name: name || null }),
    }),
  splitCluster: (id: string, claimIds: string[], name: string) =>
    request<ClaimCluster>(`/clusters/${id}/split`, {
      method: "POST",
      body: JSON.stringify({ claim_ids: claimIds, name }),
    }),
  deleteCluster: (id: string) =>
    request<void>(`/clusters/${id}`, { method: "DELETE" }),
  reanalyzeCluster: (id: string) =>
    request<ClaimCluster>(`/clusters/${id}/reanalyze`, { method: "POST" }),
  regenerateOpinionMap: (questionId: string) =>
    request(`/questions/${questionId}/generate-opinion-map`, { method: "POST" }),

  tasks: (filters: Record<string, string | number | undefined> = {}) =>
    request<Paginated<Task>>(`/tasks${queryString(filters)}`),
  task: (id: string) => request<Task>(`/tasks/${id}`),
  retryTask: (id: string) => request<Task>(`/tasks/${id}/retry`, { method: "POST" }),
  cancelTask: (id: string) => request<Task>(`/tasks/${id}/cancel`, { method: "POST" }),
  resumeTaskAfterLogin: (id: string) =>
    request<Task>(`/tasks/${id}/resume-after-login`, { method: "POST" }),
  resumeTaskAfterVerification: (id: string) =>
    request<Task>(`/tasks/${id}/resume-after-verification`, {
      method: "POST",
    }),
  workers: () => request<Worker[]>("/workers"),

  drafts: (filters: Record<string, string | number | undefined> = {}) =>
    request<Paginated<Draft>>(`/drafts${queryString(filters)}`),
  draft: (id: string) => request<Draft>(`/drafts/${id}`),
  updateDraft: (id: string, payload: Pick<Draft, "title" | "content">) =>
    request<Draft>(`/drafts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  reviewDraft: (id: string) =>
    request<Draft>(`/drafts/${id}/review`, { method: "POST" }),
  approveDraft: (id: string, reason = "") =>
    request<Draft>(`/drafts/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ action: "approve", reason }),
    }),
  rejectDraft: (id: string, reason = "") =>
    request<Draft>(`/drafts/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ action: "reject", reason }),
    }),
  regenerateDraft: (id: string) =>
    request<Draft>(`/drafts/${id}/regenerate`, { method: "POST" }),
  draftVersions: (id: string) => request<DraftVersion[]>(`/drafts/${id}/versions`),
  rewriteDraftText: (
    id: string,
    payload: {
      scope: "paragraph" | "selection";
      text: string;
      instruction: string;
    },
  ) =>
    request<{ text: string; usage: Record<string, number> }>(`/drafts/${id}/rewrite`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  imageWorkspace: (draftId: string) =>
    request<ImageWorkspace | null>(`/drafts/${draftId}/image-workspace`),
  generateImagePrompt: (
    draftId: string,
    payload: { visual_style: string; aspect_ratio: string },
  ) =>
    request<ImageWorkspace>(`/drafts/${draftId}/generate-image-prompt`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  generateInfographicContent: (
    draftId: string,
    payload: {
      template_type: "knowledge_card" | "comparison_table";
      canvas_size: "1080x1440" | "1242x1660";
    },
  ) =>
    request<ImageWorkspace>(`/drafts/${draftId}/generate-infographic-content`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateInfographic: (
    imageId: string,
    payload: {
      content: InfographicContent;
      template_type: "knowledge_card" | "comparison_table";
      canvas_size: "1080x1440" | "1242x1660";
      font_scale: number;
      brand_name: string;
      footer_text: string;
      background_position_x: number;
      background_position_y: number;
      background_scale: number;
    },
  ) =>
    request<ImageWorkspace>(`/images/${imageId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  renderInfographic: (imageId: string, version?: number) =>
    request<ImageWorkspace>(`/images/${imageId}/render`, {
      method: "POST",
      body: JSON.stringify({ version: version ?? null }),
    }),
  restoreImageVersion: (imageId: string, version: number) =>
    request<ImageWorkspace>(`/images/${imageId}/restore`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),
  markImagePromptCopied: (imageId: string, language: "zh" | "en") =>
    request<ImageWorkspace>(`/images/${imageId}/mark-copied`, {
      method: "POST",
      body: JSON.stringify({ language }),
    }),
  uploadVisualAsset: (draftId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImageWorkspace>(`/drafts/${draftId}/upload-visual-asset`, {
      method: "POST",
      body: form,
    });
  },
  deleteImageBackground: (imageId: string) =>
    request<ImageWorkspace>(`/images/${imageId}/background`, { method: "DELETE" }),
  setImageCssMode: (imageId: string, enabled: boolean) =>
    request<ImageWorkspace>(`/images/${imageId}/css-mode`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),

  settings: () => request<PublicSettings>("/settings"),
  updateSettings: (payload: Partial<PublicSettings>) =>
    request<PublicSettings>("/settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  testModel: (payload: {
    provider_mode: "mock" | "codex" | "deepseek";
    question_title: string;
    sample_answer: string;
  }) =>
    request<ModelTestResult>("/settings/test-model", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  publishReadiness: (draftId: string) =>
    request<PublishReadiness>(`/drafts/${draftId}/publish-readiness`),
  publishSchedules: () => request<PublishSchedule[]>("/publish-schedules"),
  createPublishSchedule: (payload: {
    article_draft_id: string;
    scheduled_for: string;
    mode: "manual" | "assisted";
  }) =>
    request<PublishSchedule>("/publish-schedules", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updatePublishSchedule: (
    id: string,
    payload: Partial<Pick<PublishSchedule, "scheduled_for" | "mode" | "sort_order">>,
  ) =>
    request<PublishSchedule>(`/publish-schedules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  cancelPublishSchedule: (id: string) =>
    request<PublishSchedule>(`/publish-schedules/${id}`, { method: "DELETE" }),
  executePublishSchedule: (id: string, confirmation: string) =>
    request<PublishRecord>(`/publish-schedules/${id}/execute`, {
      method: "POST",
      body: JSON.stringify({ confirmation }),
    }),
  publishRecords: () => request<PublishRecord[]>("/publish-records"),
  todayPlan: () => request<DailyPlan>("/plans/today"),
  pauseTodayPlan: () => request<{ message: string }>("/plans/today/pause", { method: "POST" }),
  continueTask: (id: string) => request<Task>(`/tasks/${id}/continue`, { method: "POST" }),
  continuePartialTask: (id: string) => request<Task>(`/tasks/${id}/continue?allow_partial=true`, { method: "POST" }),
  publishPackageUrl: (id: string) => `/api/drafts/${id}/publish-package`,
  fetchHotQuestions: () => request<{ created: number; updated: number; warnings: string[] }>("/questions/hot/fetch", { method: "POST", body: JSON.stringify({ limit: 30 }) }),
  updateTodayPlan: (payload: Partial<DailyPlan>) =>
    request<DailyPlan>("/plans/today", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  runTodayPlan: () =>
    request<{ plan: DailyPlan; queued_task_ids: string[]; message: string }>(
      "/plans/today/run",
      { method: "POST" },
    ),
  modelUsage: () => request<ModelUsageOverview>("/model-usage"),
  prompts: () => request<PromptTemplate[]>("/prompts"),
  updatePrompt: (
    id: string,
    payload: {
      content: string;
      variables: string[];
      model_role: PromptVersion["model_role"];
      parameters: Record<string, unknown>;
      change_note: string;
    },
  ) =>
    request<PromptVersion>(`/prompts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  activatePrompt: (id: string, version: number, reason: string) =>
    request<PromptTemplate>(`/prompts/${id}/activate`, {
      method: "POST",
      body: JSON.stringify({ version, reason }),
    }),
  promptVersions: (id: string) => request<PromptVersion[]>(`/prompts/${id}/versions`),
  testPrompt: (id: string, version: number | undefined, input: Record<string, unknown>) =>
    request<{
      output: string;
      provider: string;
      model: string;
      estimated_cost: number;
      duration_ms: number;
    }>(`/prompts/${id}/test`, {
      method: "POST",
      body: JSON.stringify({ version, input }),
    }),
  browserSafety: () => request<BrowserSafetyState>("/settings/browser/test"),
  browserSession: () =>
    request<ManagedBrowserSession>("/settings/browser/session"),
  startBrowserSession: () =>
    request<ManagedBrowserSession>("/settings/browser/session/start", {
      method: "POST",
    }),
  refreshBrowserSession: () =>
    request<ManagedBrowserSession>("/settings/browser/session/refresh", {
      method: "POST",
    }),
  recheckBrowserSession: () =>
    request<ManagedBrowserSession>("/settings/browser/session/recheck", {
      method: "POST",
    }),
  browserBridgeStatus: () =>
    request<BrowserBridgeStatus>("/settings/browser/bridge"),
  createBridgePairing: () =>
    request<BridgePairing>("/settings/browser/bridge/pairing", {
      method: "POST",
    }),
  unpairBridge: () =>
    request<{ revoked_clients: number; message: string }>(
      "/settings/browser/bridge/unpair",
      { method: "POST" },
    ),
  retryCollection: (taskId: string) =>
    request<{
      task_id: string;
      collection_job_id: string;
      status: string;
      dispatched: boolean;
      message: string;
    }>(`/tasks/${taskId}/retry-collection`, { method: "POST" }),
  importAnswers: (questionId: string, bundle: ImportBundleV1) =>
    request<{
      question_id: string;
      collection_job_id: string;
      resumed_task_id: string | null;
      fetched: number;
      created: number;
      updated: number;
      included: number;
      filtered: number;
      message: string;
    }>(`/questions/${questionId}/answers/import`, {
      method: "POST",
      body: JSON.stringify(bundle),
    }),
  openSourceReferences: () =>
    request<OpenSourceReference[]>("/open-source-references"),
};
