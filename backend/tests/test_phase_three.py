from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image
from sqlalchemy import select

from backend.app.db.session import get_session_factory
from backend.app.models.content import OpinionMap, QuestionScore
from backend.app.models.core import ArticleDraft, ArticleVersion, Question
from backend.app.models.media import ImageDraft, ImageTemplate, ImageVersion
from backend.app.schemas.analysis import OpinionMapData


async def _draft_fixture(*, approved: bool = False) -> str:
    async with get_session_factory()() as session:
        question = Question(
            external_id="30000001",
            title="怎样建立稳定、可持续的阅读习惯？",
            url=f"https://www.zhihu.com/question/{datetime.now().timestamp():.0f}",
            description="",
            sample_answer="",
            source="manual",
            status="review_approved" if approved else "waiting_review",
            priority="medium",
            content_hash=hashlib.sha256(
                str(datetime.now().timestamp()).encode()
            ).hexdigest(),
        )
        session.add(question)
        await session.flush()
        opinion = OpinionMapData(
            question_summary=question.title,
            one_sentence_answer="降低开始门槛，并用固定时间和反馈形成可重复的阅读节奏。",
            main_dimensions=["行动门槛", "环境触发", "反馈"],
            main_consensus=["从每天十分钟开始", "固定阅读时间和地点"],
            main_disagreements=["纸书与电子书应根据场景选择"],
            minority_but_valuable_views=["中断后直接恢复，不做补偿性阅读"],
            common_misunderstandings=["一次中断不等于习惯失败"],
            applicable_conditions=["根据工作节奏调整阅读量"],
            risks=["不要让阅读目标反过来制造压力"],
            practical_suggestions=["准备下一本书", "每天记录一句收获"],
            source_answer_ids=[],
        )
        session.add(
            OpinionMap(
                question_id=question.id,
                version=1,
                status="generated",
                content_json=opinion.model_dump(),
            )
        )
        session.add(
            QuestionScore(
                question_id=question.id,
                value_score=82,
                risk_level="normal",
                details={},
            )
        )
        draft = ArticleDraft(
            question_id=question.id,
            status="review_approved" if approved else "waiting_review",
            current_version=1,
            title=question.title,
            content="# 阅读习惯\n\n稳定比一次读很多更重要。",
            analysis_snapshot={"opinion_map": opinion.model_dump()},
            review_result={"overall_pass": True},
        )
        session.add(draft)
        await session.flush()
        session.add(
            ArticleVersion(
                draft_id=draft.id,
                version=1,
                title=draft.title,
                content=draft.content,
            )
        )
        await session.commit()
        return draft.id


@pytest.mark.asyncio
async def test_infographic_editor_render_and_download(
    app_client, tmp_path, monkeypatch
) -> None:
    _, client, _ = app_client
    import backend.app.services.infographic_renderer as renderer
    import backend.app.services.image_workflow as image_workflow

    monkeypatch.setattr(renderer, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(image_workflow, "REPOSITORY_ROOT", tmp_path)
    draft_id = await _draft_fixture()
    generated = await client.post(
        f"/api/drafts/{draft_id}/generate-infographic-content",
        json={"template_type": "comparison_table", "canvas_size": "1080x1440"},
    )
    assert generated.status_code == 200, generated.text
    workspace = generated.json()
    content = workspace["current"]["content_json"]
    assert content["title"]
    assert len(content["consensus"]) <= 4

    edited_content = {
        key: content[key]
        for key in (
            "title",
            "one_line_conclusion",
            "consensus",
            "disagreements",
            "conditions",
            "suggestions",
            "visual_keywords",
            "source_cluster_ids",
            "source_answer_ids",
        )
    }
    edited_content["suggestions"] = list(
        reversed(edited_content["suggestions"])
    )
    edited = await client.patch(
        f"/api/images/{workspace['id']}",
        json={
            "content": edited_content,
            "template_type": "comparison_table",
            "canvas_size": "1080x1440",
            "font_scale": 0.8,
            "brand_name": "知乎问题总结工作台",
            "footer_text": "AI 辅助整理，请人工核验来源",
            "background_position_x": 50,
            "background_position_y": 50,
            "background_scale": 1,
        },
    )
    assert edited.status_code == 200, edited.text

    missing_background = await client.patch(
        f"/api/images/{workspace['id']}/css-mode",
        json={"enabled": False},
    )
    assert missing_background.status_code == 409
    assert "先上传背景图" in missing_background.json()["detail"]

    rendered = await client.post(f"/api/images/{workspace['id']}/render")
    assert rendered.status_code == 200, rendered.text
    current = rendered.json()["current"]
    assert current["render_status"] == "rendered"
    assert current["overflow"] == []
    download = await client.get(current["download_url"])
    assert download.status_code == 200
    output = tmp_path / "rendered.png"
    output.write_bytes(download.content)
    with Image.open(output) as image:
        assert image.size == (1080, 1440)
        assert image.format == "PNG"


@pytest.mark.asyncio
async def test_publish_readiness_schedule_confirmation_and_safe_pause(
    app_client, tmp_path
) -> None:
    _, client, _ = app_client
    draft_id = await _draft_fixture(approved=True)
    rendered_path = tmp_path / "frozen.png"
    Image.new("RGB", (1080, 1440), "white").save(rendered_path)
    async with get_session_factory()() as session:
        template = await session.scalar(
            select(ImageTemplate).limit(1)
        )
        image_draft = ImageDraft(
            article_draft_id=draft_id,
            template_id=template.id if template else None,
            status="rendered",
            current_version=1,
            use_css_background=True,
        )
        session.add(image_draft)
        await session.flush()
        session.add(
            ImageVersion(
                image_draft_id=image_draft.id,
                version=1,
                content_json={},
                rendered_path=str(rendered_path),
                render_status="rendered",
                canvas_width=1080,
                canvas_height=1440,
            )
        )
        await session.commit()

    readiness = await client.get(
        f"/api/drafts/{draft_id}/publish-readiness"
    )
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True

    scheduled_for = datetime.now(timezone.utc) + timedelta(days=1)
    created = await client.post(
        "/api/publish-schedules",
        json={
            "article_draft_id": draft_id,
            "scheduled_for": scheduled_for.isoformat(),
            "mode": "manual",
        },
    )
    assert created.status_code == 200, created.text
    schedule = created.json()
    assert schedule["article_version"] == 1
    assert schedule["image_version"] == 1

    rejected = await client.post(
        f"/api/publish-schedules/{schedule['id']}/execute",
        json={"confirmation": "发布"},
    )
    assert rejected.status_code == 409
    confirmed = await client.post(
        f"/api/publish-schedules/{schedule['id']}/execute",
        json={"confirmation": "确认发布"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "manual_package_ready"
    schedules = await client.get("/api/publish-schedules")
    executed = next(
        item
        for item in schedules.json()
        if item["id"] == schedule["id"]
    )
    assert executed["confirmed_at"] is not None
    assert executed["executed_at"] is not None

    safety = await client.get("/api/settings/browser/test")
    assert safety.status_code == 200
    assert safety.json()["safe_to_continue"] is False
    assert safety.json()["state"] == "profile_missing"


@pytest.mark.asyncio
async def test_daily_plan_cost_prompt_versions_and_open_source(app_client) -> None:
    _, client, _ = app_client
    plan = await client.get("/api/plans/today")
    assert plan.status_code == 200
    assert plan.json()["auto_production"] is False
    assert plan.json()["auto_publish"] is False
    invalid = await client.patch(
        "/api/plans/today",
        json={"auto_publish": True, "auto_production": False},
    )
    assert invalid.status_code == 409
    run = await client.post("/api/plans/today/run")
    assert run.status_code == 200

    prompts = await client.get("/api/prompts")
    assert prompts.status_code == 200
    target = next(
        item
        for item in prompts.json()
        if item["key"] == "infographic_content_generation"
    )
    prompt_test = await client.post(
        f"/api/prompts/{target['id']}/test",
        json={
            "version": target["active_version"],
            "input": {"question_title": "如何选择适合自己的通勤方式？"},
            "provider_mode": "mock",
        },
    )
    assert prompt_test.status_code == 200, prompt_test.text
    assert prompt_test.json()["provider"] == "mock"
    assert prompt_test.json()["output"]
    version = await client.patch(
        f"/api/prompts/{target['id']}",
        json={
            "content": target["active"]["content"]
            + "\n保留所有来源 ID，且输出前自行检查长度。",
            "variables": target["active"]["variables"],
            "model_role": "fast_text_model",
            "parameters": {"temperature": 0.2},
            "change_note": "测试第三阶段不可覆盖版本",
        },
    )
    assert version.status_code == 200
    assert version.json()["version"] == 2
    rollback = await client.post(
        f"/api/prompts/{target['id']}/activate",
        json={"version": 1, "reason": "测试回滚"},
    )
    assert rollback.status_code == 200
    assert rollback.json()["active_version"] == 1
    audits = await client.get(f"/api/prompts/{target['id']}/audits")
    assert audits.status_code == 200
    assert len(audits.json()) >= 2

    usage = await client.get("/api/model-usage")
    assert usage.status_code == 200
    assert "by_stage" in usage.json()
    references = await client.get("/api/open-source-references")
    assert references.status_code == 200
    names = {item["name"] for item in references.json()}
    assert {"Microsoft Playwright", "Pillow"}.issubset(names)
