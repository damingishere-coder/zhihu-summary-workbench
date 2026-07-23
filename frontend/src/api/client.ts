import type {
  DashboardSummary,
  Draft,
  ImportResult,
  ModelTestResult,
  Paginated,
  PublicSettings,
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
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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

  tasks: (filters: Record<string, string | number | undefined> = {}) =>
    request<Paginated<Task>>(`/tasks${queryString(filters)}`),
  task: (id: string) => request<Task>(`/tasks/${id}`),
  retryTask: (id: string) => request<Task>(`/tasks/${id}/retry`, { method: "POST" }),
  cancelTask: (id: string) => request<Task>(`/tasks/${id}/cancel`, { method: "POST" }),
  workers: () => request<Worker[]>("/workers"),

  drafts: () => request<Paginated<Draft>>("/drafts"),
  draft: (id: string) => request<Draft>(`/drafts/${id}`),
  updateDraft: (id: string, payload: Pick<Draft, "title" | "content">) =>
    request<Draft>(`/drafts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  settings: () => request<PublicSettings>("/settings"),
  updateSettings: (payload: Partial<PublicSettings>) =>
    request<PublicSettings>("/settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  testModel: (payload: {
    provider_mode: "mock" | "deepseek";
    question_title: string;
    sample_answer: string;
  }) =>
    request<ModelTestResult>("/settings/test-model", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

