from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "知乎问题总结工作台"
    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    api_prefix: str = "/api"

    database_url: str = "sqlite+aiosqlite:///./data/workbench.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    queue_backend: Literal["redis", "memory"] = "redis"

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_fast_model: str = "deepseek-v4-flash"
    deepseek_reasoning_model: str = "deepseek-v4-flash"
    deepseek_fallback_model: str = "deepseek-v4-flash"
    ai_provider_mode: Literal["mock", "codex", "deepseek"] = "codex"
    ai_request_timeout_seconds: int = 60
    codex_path: str = "codex"
    codex_home: str = ""
    codex_model: str = "gpt-5.6-sol"
    codex_timeout_seconds: int = 300
    task_max_retries: int = 2
    answer_quality_batch_size: int = 8
    claim_extraction_batch_size: int = 5
    cluster_similarity_threshold: float = 0.35
    article_target_length: int = 1800
    deepseek_input_cost_per_million: float = 0
    deepseek_output_cost_per_million: float = 0
    daily_model_budget: float = 0
    pause_on_budget_exceeded: bool = True
    response_cache_enabled: bool = True

    image_generation_mode: Literal["manual"] = "manual"
    image_prompt_model_role: str = "fast_text_model"
    allow_manual_image_upload: bool = True

    embedding_provider: str = "local"
    embedding_model: str = "configurable-multilingual-embedding"

    zhihu_browser_user_data_dir: str = ""
    playwright_headless: bool = False

    daily_question_limit: int = 10
    hot_question_quota: int = 6
    manual_question_quota: int = 4
    max_answers_per_question: int = 100
    max_ai_concurrency: int = 3
    daily_plan_time: str = "09:00"
    daily_publish_limit: int = 10
    publish_interval_minutes: int = 30
    auto_production_enabled: bool = False
    auto_publish_enabled: bool = False
    infographic_render_attempts: int = 2

    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://terminal.local:4173",
    ]

    @property
    def deepseek_key_value(self) -> str | None:
        return self.deepseek_api_key.get_secret_value() if self.deepseek_api_key else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
