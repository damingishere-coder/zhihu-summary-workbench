from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.db.session import get_session_factory
from backend.app.models.content import Answer, OpinionMap
from backend.app.models.core import (
    ArticleDraft,
    ArticleVersion,
    ModelUsageLog,
    Question,
    TaskJob,
)
from backend.app.models.media import (
    ImageDraft,
    ImageVersion,
    PublishRecord,
    PublishSchedule,
)
from backend.app.services import question_deletion


async def _create_question(client, question_id: str) -> dict:
    response = await client.post(
        "/api/questions/manual",
        json={
            "url": f"https://www.zhihu.com/question/{question_id}",
            "title": f"测试问题 {question_id}",
            "description": "用于验证永久删除。",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_active_task_blocks_permanent_question_deletion(app_client) -> None:
    _, client, _ = app_client
    question = await _create_question(client, "700001")
    queued = await client.post(f"/api/questions/{question['id']}/queue")
    assert queued.status_code == 201

    deleted = await client.delete(f"/api/questions/{question['id']}")
    assert deleted.status_code == 409
    assert "先取消任务" in deleted.json()["detail"]

    existing = await client.get(f"/api/questions/{question['id']}")
    assert existing.status_code == 200


@pytest.mark.asyncio
async def test_terminal_question_deletion_removes_relations_and_controlled_files(
    app_client,
    tmp_path,
    monkeypatch,
) -> None:
    _, client, _ = app_client
    monkeypatch.setattr(question_deletion, "REPOSITORY_ROOT", tmp_path)
    question_payload = await _create_question(client, "700002")
    queued = await client.post(
        f"/api/questions/{question_payload['id']}/queue"
    )
    task_id = queued.json()["id"]

    background = tmp_path / "data" / "uploads" / "images" / "background.png"
    rendered = tmp_path / "data" / "rendered" / "images" / "rendered.png"
    screenshot = tmp_path / "data" / "publish" / "publish.png"
    for path in (background, rendered, screenshot):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"keep")

    async with get_session_factory()() as session:
        question = await session.get(Question, question_payload["id"])
        task = await session.get(TaskJob, task_id)
        task.status = "failed"
        task.stage = "failed"
        question.status = "candidate"
        session.add(
            Answer(
                question_id=question.id,
                answer_external_id="delete-answer",
                author_name="测试答主",
                plain_content="足够长的测试回答内容。",
                content_hash="a" * 64,
            )
        )
        session.add(
            OpinionMap(
                question_id=question.id,
                version=1,
                content_json={"summary": "测试"},
            )
        )
        session.add(
            ModelUsageLog(
                question_id=question.id,
                task_id=task.id,
                provider="mock",
                model_role="fast_text_model",
                model="mock",
            )
        )
        draft = ArticleDraft(
            question_id=question.id,
            title="待删除草稿",
            content="待删除正文",
        )
        session.add(draft)
        await session.flush()
        article = ArticleVersion(
            draft_id=draft.id,
            version=1,
            title=draft.title,
            content=draft.content,
            source_task_id=task.id,
        )
        image_draft = ImageDraft(
            article_draft_id=draft.id,
            status="rendered",
            current_version=1,
        )
        session.add_all([article, image_draft])
        await session.flush()
        image = ImageVersion(
            image_draft_id=image_draft.id,
            version=1,
            content_json={},
            background_path=str(background),
            rendered_path=str(rendered),
            thumbnail_path=str(outside),
            render_status="rendered",
        )
        session.add(image)
        await session.flush()
        schedule = PublishSchedule(
            article_draft_id=draft.id,
            article_version_id=article.id,
            image_version_id=image.id,
            scheduled_for=datetime.now(timezone.utc),
        )
        session.add(schedule)
        await session.flush()
        record = PublishRecord(
            schedule_id=schedule.id,
            article_version_id=article.id,
            image_version_id=image.id,
            status="prepared",
            screenshot_path=str(screenshot),
        )
        session.add(record)
        await session.commit()
        ids = {
            "draft": draft.id,
            "article": article.id,
            "image_draft": image_draft.id,
            "image": image.id,
            "schedule": schedule.id,
            "record": record.id,
        }

    deleted = await client.delete(
        f"/api/questions/{question_payload['id']}"
    )
    assert deleted.status_code == 204, deleted.text
    assert not background.exists()
    assert not rendered.exists()
    assert not screenshot.exists()
    assert outside.exists()

    async with get_session_factory()() as session:
        assert await session.get(Question, question_payload["id"]) is None
        assert await session.get(TaskJob, task_id) is None
        assert await session.get(ArticleDraft, ids["draft"]) is None
        assert await session.get(ArticleVersion, ids["article"]) is None
        assert await session.get(ImageDraft, ids["image_draft"]) is None
        assert await session.get(ImageVersion, ids["image"]) is None
        assert await session.get(PublishSchedule, ids["schedule"]) is None
        assert await session.get(PublishRecord, ids["record"]) is None
