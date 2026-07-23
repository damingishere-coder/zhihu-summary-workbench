from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.db.session import get_session_factory
from backend.app.models.content import OpinionMap
from backend.app.models.core import ArticleDraft, ArticleVersion, Question
from backend.app.models.media import ImageDraft, ImageVersion
from backend.app.schemas.analysis import OpinionMapData


@pytest.mark.asyncio
async def test_manual_image_prompt_upload_css_and_history(app_client) -> None:
    _, client, _ = app_client
    async with get_session_factory()() as session:
        question = Question(
            external_id="88776655",
            title="如何建立稳定的阅读习惯？",
            url="https://www.zhihu.com/question/88776655",
            description="",
            sample_answer="",
            source="manual",
            status="waiting_review",
            priority="medium",
            content_hash=hashlib.sha256(b"question").hexdigest(),
        )
        session.add(question)
        await session.flush()
        opinion = OpinionMapData(
            question_summary=question.title,
            one_sentence_answer="稳定习惯来自低门槛动作、固定触发和持续反馈。",
            main_dimensions=["行动门槛", "环境", "反馈"],
            main_consensus=["从每天十分钟开始", "固定阅读时间和地点"],
            main_disagreements=["纸书和电子书应按场景选择"],
            minority_but_valuable_views=["允许中断后直接恢复"],
            common_misunderstandings=["一次中断不等于习惯失败"],
            applicable_conditions=["根据工作节奏调整阅读量"],
            risks=["不要用阅读数量替代理解"],
            practical_suggestions=["准备下一本书", "记录一句收获"],
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
        draft = ArticleDraft(
            question_id=question.id,
            status="waiting_review",
            current_version=1,
            title=question.title,
            content="# 草稿\n\n正文",
            analysis_snapshot={"opinion_map": opinion.model_dump()},
            review_result={},
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
        draft_id = draft.id

    generated = await client.post(
        f"/api/drafts/{draft_id}/generate-image-prompt",
        json={"visual_style": "克制的知识编辑插画", "aspect_ratio": "3:4"},
    )
    assert generated.status_code == 200, generated.text
    workspace = generated.json()
    assert workspace["current"]["prompt_zh"]
    assert "不得生成中文" in workspace["current"]["prompt_zh"]
    assert workspace["use_css_background"] is True

    copied = await client.post(
        f"/api/images/{workspace['id']}/mark-copied",
        json={"language": "zh"},
    )
    assert copied.status_code == 200
    assert copied.json()["current"]["copy_state"]["zh"] is True

    png = b"\x89PNG\r\n\x1a\n" + b"manual-image-fixture"
    uploaded = await client.post(
        f"/api/drafts/{draft_id}/upload-visual-asset",
        files={"file": ("background.png", png, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    uploaded_workspace = uploaded.json()
    assert uploaded_workspace["use_css_background"] is False
    assert uploaded_workspace["current"]["background_url"]
    assert len(uploaded_workspace["versions"]) == 2

    asset = await client.get(uploaded_workspace["current"]["background_url"])
    assert asset.status_code == 200
    assert asset.content == png

    css_only = await client.patch(
        f"/api/images/{workspace['id']}/css-mode",
        json={"enabled": True},
    )
    assert css_only.status_code == 200
    assert css_only.json()["use_css_background"] is True

    removed = await client.delete(f"/api/images/{workspace['id']}/background")
    assert removed.status_code == 200
    assert removed.json()["current"]["background_url"] is None
    assert removed.json()["current"]["background_deleted"] is True
    assert len(removed.json()["versions"]) == 3

    async with get_session_factory()() as session:
        image_draft_id = await session.scalar(
            select(ImageDraft.id).where(ImageDraft.article_draft_id == draft_id)
        )
        paths = (
            await session.scalars(
                select(ImageVersion.background_path).where(
                    ImageVersion.image_draft_id == image_draft_id,
                    ImageVersion.background_path.is_not(None),
                )
            )
        ).all()
    for value in paths:
        Path(value).unlink(missing_ok=True)
