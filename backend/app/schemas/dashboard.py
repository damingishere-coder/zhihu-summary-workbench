from __future__ import annotations

from pydantic import BaseModel

from backend.app.schemas.task import QueueStatus, TaskLogRead, TaskRead, WorkerRead


class DashboardMetrics(BaseModel):
    today_plan: int
    processing: int
    waiting_review: int
    ready_to_publish: int
    published: int
    failed: int


class ServiceHealth(BaseModel):
    database: str
    redis: str
    workers: str
    model: str
    provider_mode: str


class DashboardSummary(BaseModel):
    metrics: DashboardMetrics
    health: ServiceHealth
    queue: QueueStatus
    workers: list[WorkerRead]
    recent_tasks: list[TaskRead]
    recent_logs: list[TaskLogRead]

