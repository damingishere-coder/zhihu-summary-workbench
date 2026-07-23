from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    level: str
    stage: str
    message: str
    metadata_json: dict[str, Any]
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    question_title: str = ""
    task_type: str
    status: str
    stage: str
    progress: int
    worker_id: str | None
    retry_count: int
    max_retries: int
    result: dict[str, Any]
    error_message: str | None
    cancel_requested: bool
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    logs: list[TaskLogRead] = []


class TaskListResponse(BaseModel):
    items: list[TaskRead]
    total: int


class QueueStatus(BaseModel):
    connected: bool
    backend: str
    queued: int
    channel: str
    latency_ms: int | None = None
    error: str | None = None


class WorkerRead(BaseModel):
    worker_id: str
    state: str
    current_task_id: str | None = None
    heartbeat_at: datetime
    stale: bool = False

