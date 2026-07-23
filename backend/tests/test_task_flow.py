from __future__ import annotations

import pytest

from backend.app.collectors.zhihu import (
    CollectedAnswer,
    CollectedQuestion,
    ZhihuFetchResult,
    clean_answer_html,
)
from backend.app.core.config import get_settings
from backend.app.db.session import get_session_factory
from backend.app.services.tasks import process_task


class FakeZhihuCollector:
    async def fetch_question_and_answers(self, question_id, **_kwargs):
        answers = []
        themes = [
            "从很小的行动开始并固定触发时间，比依赖短期意志力更可靠",
            "记录完成情况可以形成反馈，但不要因为一天中断就完全放弃",
            "环境设计会影响执行难度，应提前准备器材并减少干扰",
            "目标需要符合当前体能，过高强度会增加受伤和退出风险",
            "有人适合结伴监督，也有人更适合独立完成，需要结合性格选择",
        ]
        for index in range(24):
            body = (
                f"<p>{themes[index % len(themes)]}。</p>"
                f"<p>第 {index + 1} 位回答者强调：如果工作日时间紧张，"
                "先完成十分钟低强度训练，再根据状态逐步增加；长期稳定比一次做到完美更重要。</p>"
            )
            plain, markdown, media = clean_answer_html(body)
            answers.append(
                CollectedAnswer(
                    external_id=f"answer-{index + 1}",
                    author_name=f"答主 {index + 1}",
                    author_url=f"https://www.zhihu.com/people/test-{index + 1}",
                    answer_url=(
                        f"https://www.zhihu.com/question/{question_id}/answer/{index + 1}"
                    ),
                    html_content=body,
                    markdown_content=markdown,
                    plain_content=plain,
                    content_hash=f"{index + 1:064x}",
                    vote_count=500 - index * 7,
                    comment_count=30 + index,
                    published_at=None,
                    updated_at=None,
                    sort_order=index,
                    media=media,
                    raw_snapshot={"id": f"answer-{index + 1}"},
                )
            )
        return ZhihuFetchResult(
            question=CollectedQuestion(
                external_id=question_id,
                title="普通人如何形成长期有效的运动习惯？",
                url=f"https://www.zhihu.com/question/{question_id}",
                description="关注可执行性、持续性与个体差异。",
                answer_count=24,
                follower_count=1200,
                raw_snapshot={"id": question_id},
            ),
            answers=answers,
            collector_mode="test_fixture",
        )


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
        collector=FakeZhihuCollector(),
    )

    task_response = await client.get(f"/api/tasks/{task_id}")
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["status"] == "waiting_review"
    assert task["progress"] == 100
    assert task["result"]["fetch"]["fetched"] == 24
    assert task["result"]["claims"]["claims"] >= 20
    assert task["result"]["clusters"]["clusters"] >= 1
    assert task["result"]["review"]["requires_human_review"] is True
    assert task["worker_id"] == "test-worker-01"
    assert len(task["logs"]) >= 12

    answers = await client.get(f"/api/questions/{question['id']}/answers")
    assert answers.status_code == 200
    assert answers.json()["total"] == 24
    analysis = await client.get(f"/api/questions/{question['id']}/analysis")
    assert analysis.status_code == 200
    assert analysis.json()["opinion_map"]["main_consensus"]

    draft_response = await client.get(
        f"/api/drafts/{task['result']['draft_id']}"
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["status"] == "waiting_review"
    assert "多回答综合总结" in draft["title"]
    assert draft["paragraph_sources"]
    assert draft["review_result"]["requires_human_review"] is True

    cluster = analysis.json()["clusters"][0]
    assert cluster["sources"]
    split = await client.post(
        f"/api/clusters/{cluster['id']}/split",
        json={
            "claim_ids": cluster["claim_ids"][:1],
            "name": "人工拆分观点",
        },
    )
    assert split.status_code == 200, split.text
    merged = await client.post(
        "/api/clusters/merge",
        json={
            "cluster_ids": [cluster["id"], split.json()["id"]],
            "name": "人工合并观点",
        },
    )
    assert merged.status_code == 200, merged.text
    updated_cluster = await client.patch(
        f"/api/clusters/{merged.json()['id']}",
        json={
            "name": "人工调整后的核心观点",
            "sort_order": 0,
            "write_policy": "force",
        },
    )
    assert updated_cluster.status_code == 200, updated_cluster.text
    assert updated_cluster.json()["write_policy"] == "force"
    assert updated_cluster.json()["sort_order"] == 0
    reanalyzed = await client.post(
        f"/api/clusters/{merged.json()['id']}/reanalyze"
    )
    assert reanalyzed.status_code == 200, reanalyzed.text
    regenerated_map = await client.post(
        f"/api/questions/{question['id']}/generate-opinion-map"
    )
    assert regenerated_map.status_code == 200, regenerated_map.text

    rewritten = await client.post(
        f"/api/drafts/{draft['id']}/rewrite",
        json={
            "scope": "selection",
            "text": "长期稳定更重要。长期稳定更重要。",
            "instruction": "更简洁，但不要改变原意。",
        },
    )
    assert rewritten.status_code == 200, rewritten.text
    assert rewritten.json()["text"] == "长期稳定更重要。"
    assert rewritten.json()["usage"]["calls"] >= 14

    approved = await client.post(
        f"/api/drafts/{draft['id']}/approve",
        json={"action": "approve", "reason": "已核验来源"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "review_approved"

    edited = await client.patch(
        f"/api/drafts/{draft['id']}",
        json={"title": f"{draft['title']}（编辑版）", "content": draft["content"]},
    )
    assert edited.status_code == 200
    assert edited.json()["status"] == "waiting_review"
    assert edited.json()["review_result"] == {}


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
