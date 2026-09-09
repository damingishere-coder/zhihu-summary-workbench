from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select

from backend.app.ai.providers.codex_image import CodexImageProvider
from backend.app.core.config import REPOSITORY_ROOT
from backend.app.models.media import ImageVersion
from backend.app.models.core import ModelUsageLog
from backend.app.services.checkpoints import checkpoint
from backend.app.services.image_workflow import (
    generate_prompt_version, get_image_workspace, upload_background, resolve_rendered_path,
)
from backend.app.services.infographic_renderer import render_image_workspace
from backend.app.services.settings import configured_settings_copy


async def produce_task_images(session, broker, task, draft, settings):
    from backend.app.services.tasks import _set_progress
    # ORM drafts recovered from a checkpoint may not have their relationship loaded.
    await session.refresh(draft, ["question"])
    await _set_progress(session, broker, task, stage="generating_image", progress=95, message="正在准备与文章版本一致的信息图")
    await checkpoint(session, task, "image_prompt", lambda: generate_prompt_version(
        session, draft, settings, visual_style="克制的知识编辑插画", aspect_ratio="3:4"
    ), encode=lambda value: {"image_id": value.id})
    image_draft = await get_image_workspace(session, draft.id)
    current = await session.scalar(select(ImageVersion).where(
        ImageVersion.image_draft_id == image_draft.id, ImageVersion.version == image_draft.current_version))
    if current.copy_state.get("article_version") != draft.current_version:
        raise ValueError("信息图对应的文章版本已变化，请重新生成当前文章的信息图")
    if current.content_json.get('opinion_survey'):
        await _set_progress(session, broker, task, stage="rendering_image", progress=98, message="正在用已核算的作者人数绘制观点统计图")
        await checkpoint(session, task, "image_render", lambda: render_image_workspace(session, image_draft, settings),
                         encode=lambda value: {"image_id": value.id, "version": value.current_version})
        await session.refresh(current)
        if current.render_status != 'rendered':
            raise ValueError('观点统计图尚未完成渲染')
        resolve_rendered_path(current)
        task.result = {**task.result, "images_complete": True, "image_id": image_draft.id,
                       "image_article_version": draft.current_version}
        draft.analysis_snapshot = {**draft.analysis_snapshot, "image_article_version": draft.current_version}
        await session.commit()
        return
    current.workflow_mode = "codex_cli"
    current.content_json = {**current.content_json, "auto_fit": True}
    await session.commit()
    runtime = await configured_settings_copy(session, settings)
    folder = REPOSITORY_ROOT / "data" / "generated" / task.id
    async def generate_background():
        try:
            return await CodexImageProvider(runtime).generate(current.prompt_zh, folder)
        finally:
            if (folder / "generation.json").is_file():
                recorded = await session.scalar(select(ModelUsageLog.id).where(ModelUsageLog.task_id == task.id, ModelUsageLog.stage == "generating_image").limit(1))
                if not recorded:
                    session.add(ModelUsageLog(task_id=task.id, question_id=task.question_id,
                        stage="generating_image", provider="codex_cli", model_role="image",
                        model="native_image_unreported"))
                    await session.commit()
    artifact = await checkpoint(session, task, "image_generation", generate_background)
    if "image_upload" not in task.result.get("checkpoints", {}):
        upload = UploadFile(filename="codex-background.png", file=BytesIO(Path(artifact["path"]).read_bytes()))
        try:
            await checkpoint(session, task, "image_upload", lambda: upload_background(session, image_draft, upload),
                             encode=lambda value: {"image_id": value.id, "version": value.current_version})
        finally:
            await upload.close()
    await _set_progress(session, broker, task, stage="rendering_image", progress=98, message="正在排版中文并检查信息图溢出")
    async def render_fitted():
        for scale in (1, .9, .8, .75):
            version = await session.scalar(select(ImageVersion).where(ImageVersion.image_draft_id == image_draft.id, ImageVersion.version == image_draft.current_version))
            if scale < 1:
                version.canvas_width, version.canvas_height = 1242, 1660
                version.content_json = {**version.content_json, "font_scale": scale, "canvas_size": "1242x1660"}
                await session.commit()
            try:
                return await render_image_workspace(session, image_draft, settings)
            except ValueError:
                if version.render_status != "overflow" or scale == .75:
                    raise
    await checkpoint(session, task, "image_render", render_fitted,
                     encode=lambda value: {"image_id": value.id, "version": value.current_version})
    rendered = await session.scalar(select(ImageVersion).where(ImageVersion.image_draft_id == image_draft.id, ImageVersion.version == image_draft.current_version))
    if rendered.render_status != "rendered":
        raise ValueError("信息图尚未完成渲染，不能计为完整产出")
    resolve_rendered_path(rendered)
    task.result = {**task.result, "images_complete": True, "image_id": image_draft.id,
                   "image_article_version": draft.current_version}
    draft.analysis_snapshot = {**draft.analysis_snapshot, "image_article_version": draft.current_version}
    await session.commit()
