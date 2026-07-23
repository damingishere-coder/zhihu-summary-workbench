export type Priority = "high" | "medium" | "low";

export interface Question {
  id: string;
  external_id: string | null;
  title: string;
  url: string;
  description: string;
  sample_answer: string;
  source: string;
  status: string;
  priority: Priority;
  created_at: string;
  updated_at: string;
  latest_task_id?: string | null;
  latest_draft_id?: string | null;
}

export interface TaskLog {
  id: string;
  level: string;
  stage: string;
  message: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface ClaimAnalysis {
  summary: string;
  core_claims: string[];
  supporting_reasons: string[];
  position: string;
  risks_or_limitations: string[];
  quality_score: number;
  relevance_score: number;
}

export interface Task {
  id: string;
  question_id: string;
  question_title: string;
  task_type: string;
  status: string;
  stage: string;
  progress: number;
  worker_id: string | null;
  retry_count: number;
  max_retries: number;
  result: {
    analysis?: ClaimAnalysis;
    draft_id?: string;
    provider?: string;
    model?: string;
  };
  error_message: string | null;
  cancel_requested: boolean;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  logs: TaskLog[];
}

export interface Draft {
  id: string;
  question_id: string;
  question_title: string;
  status: string;
  current_version: number;
  title: string;
  content: string;
  analysis_snapshot: ClaimAnalysis;
  created_at: string;
  updated_at: string;
}

export interface QueueStatus {
  connected: boolean;
  backend: string;
  queued: number;
  channel: string;
  latency_ms: number | null;
  error: string | null;
}

export interface Worker {
  worker_id: string;
  state: string;
  current_task_id: string | null;
  heartbeat_at: string;
  stale: boolean;
}

export interface PublicSettings {
  provider_mode: "mock" | "deepseek";
  deepseek_configured: boolean;
  deepseek_base_url: string;
  fast_text_model: string;
  reasoning_model: string;
  fallback_text_model: string;
  embedding_provider: string;
  embedding_model: string;
  image_generation_mode: string;
  allow_manual_image_upload: boolean;
  daily_question_limit: number;
  max_ai_concurrency: number;
  request_timeout_seconds: number;
  browser_user_data_dir: string;
  redis_url_display: string;
}

export interface ModelTestResult {
  success: boolean;
  provider: string;
  model: string;
  message: string;
  analysis: ClaimAnalysis | null;
  usage: {
    input_tokens: number;
    output_tokens: number;
    duration_ms: number;
    estimated_cost: number;
  } | null;
}

export interface DashboardSummary {
  metrics: {
    today_plan: number;
    processing: number;
    waiting_review: number;
    ready_to_publish: number;
    published: number;
    failed: number;
  };
  health: {
    database: string;
    redis: string;
    workers: string;
    model: string;
    provider_mode: string;
  };
  queue: QueueStatus;
  workers: Worker[];
  recent_tasks: Task[];
  recent_logs: TaskLog[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
}

export interface ImportResult {
  created: number;
  duplicate: number;
  failed: number;
  items: Array<{
    url: string;
    status: "created" | "duplicate" | "failed";
    question_id: string | null;
    message: string;
  }>;
}

