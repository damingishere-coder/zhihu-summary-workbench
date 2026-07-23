from __future__ import annotations

import pytest

from backend.app.core.config import get_settings
from backend.app.db.session import get_session_factory
from backend.app.services.tasks import process_task


@pytest.mark.asyncio
async def test_real_minimum_task_flow_with_mock_provider(app_client) -> None:
    _, client, broker = app_client
    created = await client.post(
        "/api/questions/manual",
        json={
            "url": "https://www.zhihu.com/question/22334455",
            "title": "普通人如何形成长期有效的运动习惯？",
            "description": "关注可执行性和持续反馈。",
            "sample_answer": "从每周两次开始。选择阻力最小的运动。记录完成情况，并按月调整。",
            "priority": "high",
        },
    )
    question = created.json()

    queued = await client.post(f"/api/questions/{question['id']}/queue")
    assert queued.status_code == 201, queued.text
    task_id = queued.json()["id"]
    assert queued.json()["status"] == "queued"
    assert await broker.dequeue(timeout=1) == task_id

    await process_task(
        task_id,
        worker_id="test-worker-01",
        settings=get_settings(),
        broker=broker,
        session_factory=get_session_factory(),
    )

    task_response = await client.get(f"/api/tasks/{task_id}")
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["status"] == "waiting_review"
    assert task["progress"] == 100
    assert task["result"]["analysis"]["core_claims"]
    assert task["result"]["provider"] == "mock"
    assert len(task["logs"]) >= 4

    draft_response = await client.get(
        f"/api/drafts/{task['result']['draft_id']}"
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["status"] == "waiting_review"
    assert "第一阶段最小草稿" in draft["content"]


@pytest.mark.asyncio
async def test_cancelled_task_can_retry_and_preserves_retry_count(app_client) -> None:
    _, client, broker = app_client
    created = await client.post(
        "/api/questions/manual",
        json={
            "url": "https://www.zhihu.com/question/55667788",
            "title": "如何验证任务重试？",
            "sample_answer": "第一次取消，第二次重新进入队列。",
        },
    )
    question_id = created.json()["id"]
    queued = await client.post(f"/api/questions/{question_id}/queue")
    task_id = queued.json()["id"]

    cancelled = await client.post(f"/api/tasks/{task_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    retried = await client.post(f"/api/tasks/{task_id}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "queued"
    assert retried.json()["retry_count"] == 1

