from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.ai.providers.factory import create_text_provider
from backend.app.core.config import Settings
from backend.app.models.core import (
    AuditLog,
    ModelUsageLog,
    PromptTemplate,
    PromptVersion,
)
from backend.app.schemas.prompt import (
    PromptActivateRequest,
    PromptAuditRead,
    PromptCreate,
    PromptTemplateRead,
    PromptTestRequest,
    PromptTestResponse,
    PromptUpdate,
    PromptVersionRead,
)
from backend.app.services.settings import (
    configured_settings_copy,
    provider_mode,
)


def version_to_read(version: PromptVersion) -> PromptVersionRead:
    return PromptVersionRead(
        id=version.id,
        version=version.version,
        content=version.content,
        variables=version.variables or [],
        model_role=version.model_role,
        parameters=version.parameters or {},
        is_active=version.is_active,
        test_input=version.test_input or {},
        test_output=version.test_output,
        change_note=version.change_note,
        created_by=version.created_by,
        created_at=version.created_at,
    )


def template_to_read(template: PromptTemplate) -> PromptTemplateRead:
    versions = list(template.versions)
    active = next(
        (item for item in versions if item.version == template.active_version),
        None,
    )
    return PromptTemplateRead(
        id=template.id,
        key=template.key,
        name=template.name,
        description=template.description,
        active_version=template.active_version,
        version_count=len(versions),
        active=version_to_read(active) if active else None,
    )


async def list_prompt_templates(
    session: AsyncSession,
) -> list[PromptTemplateRead]:
    items = (
        await session.scalars(
            select(PromptTemplate)
            .options(selectinload(PromptTemplate.versions))
            .order_by(PromptTemplate.name)
        )
    ).all()
    return [template_to_read(item) for item in items]


async def list_prompt_versions(
    session: AsyncSession, prompt_id: str
) -> list[PromptVersionRead]:
    items = (
        await session.scalars(
            select(PromptVersion)
            .where(PromptVersion.template_id == prompt_id)
            .order_by(PromptVersion.version.desc())
        )
    ).all()
    return [version_to_read(item) for item in items]


async def get_active_prompt(
    session: AsyncSession, key: str, default: str
) -> str:
    template = await session.scalar(
        select(PromptTemplate).where(PromptTemplate.key == key)
    )
    if not template:
        return default
    version = await session.scalar(
        select(PromptVersion).where(
            PromptVersion.template_id == template.id,
            PromptVersion.version == template.active_version,
        )
    )
    return version.content if version else default


async def create_prompt(
    session: AsyncSession, payload: PromptCreate
) -> PromptTemplateRead:
    if await session.scalar(
        select(PromptTemplate.id).where(PromptTemplate.key == payload.key)
    ):
        raise ValueError("Prompt key 已存在")
    template = PromptTemplate(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        active_version=1,
    )
    session.add(template)
    await session.flush()
    version = PromptVersion(
        template_id=template.id,
        version=1,
        content=payload.content,
        variables=payload.variables,
        model_role=payload.model_role,
        parameters=payload.parameters,
        is_active=True,
        change_note=payload.change_note,
        created_by="operator",
    )
    session.add(version)
    session.add(
        AuditLog(
            actor="operator",
            action="prompt.create",
            entity_type="prompt_template",
            entity_id=template.id,
            after_data={"key": template.key, "version": 1},
        )
    )
    await session.commit()
    template = await session.scalar(
        select(PromptTemplate)
        .options(selectinload(PromptTemplate.versions))
        .where(PromptTemplate.id == template.id)
    )
    assert template is not None
    return template_to_read(template)


async def create_prompt_version(
    session: AsyncSession,
    template: PromptTemplate,
    payload: PromptUpdate,
) -> PromptVersionRead:
    latest = int(
        (
            await session.scalar(
                select(func.max(PromptVersion.version)).where(
                    PromptVersion.template_id == template.id
                )
            )
        )
        or 0
    )
    before = {
        "name": template.name,
        "description": template.description,
        "active_version": template.active_version,
    }
    if payload.name is not None:
        template.name = payload.name
    if payload.description is not None:
        template.description = payload.description
    version = PromptVersion(
        template_id=template.id,
        version=latest + 1,
        content=payload.content,
        variables=payload.variables,
        model_role=payload.model_role,
        parameters=payload.parameters,
        is_active=False,
        change_note=payload.change_note,
        created_by="operator",
    )
    session.add(version)
    await session.flush()
    session.add(
        AuditLog(
            actor="operator",
            action="prompt.version.create",
            entity_type="prompt_template",
            entity_id=template.id,
            before_data=before,
            after_data={
                "version": version.version,
                "change_note": version.change_note,
            },
        )
    )
    await session.commit()
    return version_to_read(version)


async def activate_prompt_version(
    session: AsyncSession,
    template: PromptTemplate,
    payload: PromptActivateRequest,
) -> PromptTemplateRead:
    target = await session.scalar(
        select(PromptVersion).where(
            PromptVersion.template_id == template.id,
            PromptVersion.version == payload.version,
        )
    )
    if not target:
        raise ValueError("要启用的 Prompt 版本不存在")
    before_version = template.active_version
    versions = (
        await session.scalars(
            select(PromptVersion).where(
                PromptVersion.template_id == template.id
            )
        )
    ).all()
    for version in versions:
        version.is_active = version.id == target.id
    template.active_version = target.version
    session.add(
        AuditLog(
            actor="operator",
            action=(
                "prompt.rollback"
                if target.version < before_version
                else "prompt.activate"
            ),
            entity_type="prompt_template",
            entity_id=template.id,
            before_data={"active_version": before_version},
            after_data={
                "active_version": target.version,
                "reason": payload.reason,
            },
        )
    )
    await session.commit()
    template = await session.scalar(
        select(PromptTemplate)
        .options(selectinload(PromptTemplate.versions))
        .where(PromptTemplate.id == template.id)
    )
    assert template is not None
    return template_to_read(template)


async def test_prompt(
    session: AsyncSession,
    template: PromptTemplate,
    payload: PromptTestRequest,
    settings: Settings,
) -> PromptTestResponse:
    version_number = payload.version or template.active_version
    version = await session.scalar(
        select(PromptVersion).where(
            PromptVersion.template_id == template.id,
            PromptVersion.version == version_number,
        )
    )
    if not version:
        raise ValueError("要测试的 Prompt 版本不存在")
    runtime = await configured_settings_copy(session, settings)
    mode = payload.provider_mode or await provider_mode(session, settings)
    provider = create_text_provider(mode, runtime)
    output, usage = await provider.generate_text(
        system_prompt=version.content,
        user_prompt="测试输入 JSON：\n"
        + json.dumps(payload.input, ensure_ascii=False),
        model_role=version.model_role,
    )
    version.test_input = payload.input
    version.test_output = output[:20_000]
    session.add(
        ModelUsageLog(
            question_id=None,
            task_id=None,
            provider=usage.provider,
            model_role=usage.model_role,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost=Decimal(str(usage.estimated_cost)),
            duration_ms=usage.duration_ms,
            status="success",
            stage="prompt_test",
            cache_hit=usage.cache_hit,
            fallback_used=usage.fallback_used,
            retry_count=usage.retry_count,
        )
    )
    session.add(
        AuditLog(
            actor="operator",
            action="prompt.test",
            entity_type="prompt_template",
            entity_id=template.id,
            after_data={"version": version.version, "provider": usage.provider},
        )
    )
    await session.commit()
    return PromptTestResponse(
        output=output,
        provider=usage.provider,
        model=usage.model,
        model_role=usage.model_role,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        estimated_cost=usage.estimated_cost,
        duration_ms=usage.duration_ms,
    )


async def prompt_audits(
    session: AsyncSession, prompt_id: str
) -> list[PromptAuditRead]:
    items = (
        await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "prompt_template",
                AuditLog.entity_id == prompt_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        PromptAuditRead(
            id=item.id,
            action=item.action,
            before_data=item.before_data or {},
            after_data=item.after_data or {},
            actor=item.actor,
            created_at=item.created_at,
        )
        for item in items
    ]
