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
  hot_rank: number | null;
  hot_score: string;
  answer_count: number;
  follower_count: number;
  fetched_at: string | null;
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

export interface CaptureDiagnostic {
  code: string;
  level: "info" | "warning" | "error";
  message: string;
}

export interface CaptureSummary {
  stop_reason?: string;
  reached_end?: boolean;
  version?: number | null;
  method?: string | null;
  page_url?: string | null;
  visible_answer_count?: number | null;
  collected_answer_count?: number | null;
  diagnostics?: CaptureDiagnostic[];
  recommended_action?: string;
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
    fetch?: Record<string, number>;
    quality?: Record<string, number>;
    claims?: Record<string, number>;
    embeddings?: Record<string, number>;
    clusters?: Record<string, number>;
    collector_mode?: string;
    capture?: CaptureSummary;
    warnings?: string[];
    article_characters?: number;
    review?: ArticleQualityReview;
    usage?: ModelUsageSummary;
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
  analysis_snapshot: Record<string, unknown> & {
    opinion_map?: OpinionMap;
    answer_count?: number;
    cluster_count?: number;
    core_claims?: string[];
    quality_score?: number;
    relevance_score?: number;
  };
  review_result: ArticleQualityReview | Record<string, never>;
  reviewed_at: string | null;
  paragraph_sources: ParagraphSource[];
  created_at: string;
  updated_at: string;
}

export interface Answer {
  id: string;
  question_id: string;
  answer_external_id: string;
  author_name: string;
  author_url: string;
  answer_url: string;
  markdown_content: string;
  plain_content: string;
  vote_count: number;
  comment_count: number;
  published_at: string | null;
  external_updated_at: string | null;
  sort_order: number;
  media_json: {
    images?: string[];
    videos?: string[];
    formulas?: string[];
  };
  fetch_batch: string;
  included_for_analysis: boolean;
  filter_reason: string;
  created_at: string;
  updated_at: string;
  analysis: null | {
    summary?: string;
    core_claims?: string[];
    quality_score?: number;
    relevance_score?: number;
    information_density?: number;
    include?: boolean;
    reason?: string;
  };
}

export interface AnswerList {
  items: Answer[];
  total: number;
  included: number;
  filtered: number;
}

export interface OpinionMap {
  question_summary: string;
  one_sentence_answer: string;
  main_dimensions: string[];
  main_consensus: string[];
  main_disagreements: string[];
  minority_but_valuable_views: string[];
  common_misunderstandings: string[];
  applicable_conditions: string[];
  risks: string[];
  practical_suggestions: string[];
  source_answer_ids: string[];
}

export interface ClaimCluster {
  id: string;
  question_id: string;
  name: string;
  summary: string;
  cluster_type: string;
  confidence: number;
  support_count: number;
  opposing_reasons: string[];
  applicable_conditions: string[];
  is_mainstream: boolean;
  is_minority: boolean;
  is_controversial: boolean;
  information_gain: number;
  sort_order: number;
  write_policy: "auto" | "force" | "exclude";
  source_answer_ids: string[];
  claim_ids: string[];
  sources: Array<{
    answer_id: string;
    author_name: string;
    answer_url: string;
    excerpt: string;
  }>;
}

export interface ModelUsageSummary {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  duration_ms: number;
}

export interface AnalysisOverview {
  question_id: string;
  answers_total: number;
  answers_included: number;
  clusters: ClaimCluster[];
  opinion_map: OpinionMap | null;
  opinion_map_version: number | null;
  model_usage: ModelUsageSummary;
  latest_draft_id: string | null;
}

export interface ArticleQualityReview {
  passed: boolean;
  score: number;
  checks: Record<string, boolean>;
  issues: string[];
  risk_level: "normal" | "high";
  requires_human_review: boolean;
  summary: string;
}

export interface ParagraphSource {
  paragraph_id: string;
  answer_id: string | null;
  answer_author: string | null;
  answer_url: string | null;
  answer_excerpt: string | null;
  cluster_id: string | null;
  cluster_name: string | null;
}

export interface ImageVersion {
  id: string;
  version: number;
  content_json: {
    title?: string;
    one_line_conclusion?: string;
    consensus?: Array<{ title: string; description: string }>;
    disagreements?: string[];
    conditions?: string[];
    suggestions?: string[];
    suggested_size?: string;
    aspect_ratio?: string;
    negative_constraints?: string[];
    visual_keywords?: string[];
    source_cluster_ids?: string[];
    source_answer_ids?: string[];
    template_type?: "knowledge_card" | "comparison_table";
    canvas_size?: "1080x1440" | "1242x1660";
    font_scale?: number;
    brand_name?: string;
    footer_text?: string;
    background_position_x?: number;
    background_position_y?: number;
    background_scale?: number;
  };
  prompt_zh: string;
  prompt_en: string;
  background_url: string | null;
  thumbnail_url: string | null;
  rendered_url: string | null;
  download_url: string | null;
  html_snapshot_available: boolean;
  render_status: string;
  canvas_width: number;
  canvas_height: number;
  overflow: Array<Record<string, unknown>>;
  render_log: Array<{ at: string; level: string; message: string }>;
  uploaded_name: string | null;
  content_type: string | null;
  byte_size: number;
  background_deleted: boolean;
  copy_state: Record<string, boolean>;
  created_at: string;
}

export interface ImageWorkspace {
  id: string;
  article_draft_id: string;
  status: string;
  current_version: number;
  use_css_background: boolean;
  current: ImageVersion | null;
  versions: ImageVersion[];
  templates: Array<{
    id: string;
    name: string;
    template_type: "knowledge_card" | "comparison_table";
    schema_json: Record<string, unknown>;
    enabled: boolean;
  }>;
}

export interface InfographicContent {
  title: string;
  one_line_conclusion: string;
  consensus: Array<{ title: string; description: string }>;
  disagreements: string[];
  conditions: string[];
  suggestions: string[];
  visual_keywords: string[];
  source_cluster_ids: string[];
  source_answer_ids: string[];
}

export interface PublishReadiness {
  draft_id: string;
  ready: boolean;
  article_approved: boolean;
  article_version_id: string | null;
  article_version: number | null;
  image_rendered: boolean;
  image_version_id: string | null;
  image_version: number | null;
  risk_level: string;
  blockers: string[];
  warnings: string[];
}

export interface PublishSchedule {
  id: string;
  article_draft_id: string;
  article_title: string;
  article_version_id: string | null;
  article_version: number | null;
  image_version_id: string | null;
  image_version: number | null;
  scheduled_for: string;
  mode: "manual" | "assisted";
  status: string;
  requires_confirmation: boolean;
  sort_order: number;
  interval_minutes: number;
  conflict_state: { has_conflict?: boolean; messages?: string[] };
  confirmed_at: string | null;
  confirmed_by: string | null;
  executed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublishRecord {
  id: string;
  schedule_id: string | null;
  article_version_id: string | null;
  image_version_id: string | null;
  status: string;
  final_url: string | null;
  error_message: string | null;
  screenshot_url: string | null;
  attempt_count: number;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DailyPlan {
  id: string;
  plan_date: string;
  question_limit: number;
  hot_quota: number;
  manual_quota: number;
  status: string;
  execute_time: string;
  max_concurrency: number;
  max_answers: number;
  daily_publish_limit: number;
  publish_interval_minutes: number;
  auto_production: boolean;
  auto_publish: boolean;
  last_executed_at: string | null;
  result: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface UsageBreakdown {
  key: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
}

export interface ModelUsageOverview {
  cost_known?: boolean;
  usage_known?: boolean;
  date: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  daily_budget: number;
  budget_remaining: number | null;
  budget_exceeded: boolean;
  cache_hits: number;
  fallback_calls: number;
  retries: number;
  manual_image_generations: number;
  by_stage: UsageBreakdown[];
  by_question: UsageBreakdown[];
}

export interface PromptVersion {
  id: string;
  version: number;
  content: string;
  variables: string[];
  model_role: "fast_text_model" | "reasoning_model" | "fallback_text_model";
  parameters: Record<string, unknown>;
  is_active: boolean;
  test_input: Record<string, unknown>;
  test_output: string;
  change_note: string;
  created_by: string;
  created_at: string;
}

export interface PromptTemplate {
  id: string;
  key: string;
  name: string;
  description: string;
  active_version: number;
  version_count: number;
  active: PromptVersion | null;
}

export interface BrowserSafetyState {
  adapter: string;
  state: string;
  safe_to_continue: boolean;
  message: string;
  profile_configured: boolean;
  screenshot_url: string | null;
}

export interface ManagedBrowserSession {
  state:
    | "idle"
    | "starting"
    | "qr_ready"
    | "scanned"
    | "authenticated"
    | "expired"
    | "verification_required"
    | "failed";
  authenticated: boolean;
  message: string;
  qr_code_url: string | null;
  updated_at: string;
}

export interface BrowserBridgeStatus {
  connection: "connected" | "disconnected" | "unpaired";
  zhihu_auth:
    | "authenticated"
    | "login_required"
    | "verification_required"
    | "unknown";
  extension_version: string;
  last_seen_at: string | null;
  last_check_at: string | null;
  active_job_id: string | null;
  latest_capture: (CaptureSummary & {
    job_id: string;
    status: string;
    source: string;
    capture_version?: number | null;
    capture_method?: string | null;
  }) | null;
  message: string;
}

export interface BridgePairing {
  pairing_code: string;
  expires_at: string;
  websocket_url: string;
  message: string;
}

export interface ImportBundleV1 {
  format: "ImportBundleV1";
  version: 1;
  collected_at: string;
  mode: "representative" | "complete";
  question: {
    id: string;
    title: string;
    url?: string;
    detail?: string;
    excerpt?: string;
    answer_count?: number;
    follower_count?: number;
  };
  answers: Array<{
    id: string;
    question_id: string;
    author?: { name?: string; url_token?: string };
    url?: string;
    content?: string;
    voteup_count?: number;
    comment_count?: number;
    created_time?: number | null;
    updated_time?: number | null;
  }>;
  warnings?: string[];
}

export interface OpenSourceReference {
  id: string;
  name: string;
  version: string;
  license_name: string;
  source_url: string;
  usage_note: string;
  created_at: string;
}

export interface DraftVersion {
  id: string;
  version: number;
  title: string;
  content: string;
  source_task_id: string | null;
  created_at: string;
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
  provider_mode: "mock" | "codex" | "deepseek";
  codex_configured: boolean;
  codex_model: string;
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
  hot_question_quota: number;
  manual_question_quota: number;
  max_answers_per_question: number;
  max_ai_concurrency: number;
  request_timeout_seconds: number;
  daily_plan_time: string;
  daily_publish_limit: number;
  publish_interval_minutes: number;
  auto_production_enabled: boolean;
  auto_publish_enabled: boolean;
  daily_model_budget: number;
  pause_on_budget_exceeded: boolean;
  response_cache_enabled: boolean;
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
