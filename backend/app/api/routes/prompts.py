from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.db.session import get_db_session
from backend.app.models.core import PromptTemplate, PromptVersion


router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("")
async def list_prompts(
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    items = (
        await session.scalars(
            select(PromptTemplate)
            .options(selectinload(PromptTemplate.versions))
            .order_by(PromptTemplate.name)
        )
    ).all()
    return [
        {
            "id": item.id,
            "key": item.key,
            "name": item.name,
            "description": item.description,
            "active_version": item.active_version,
            "version_count": len(item.versions),
        }
        for item in items
    ]


@router.get("/{prompt_id}/versions")
async def list_prompt_versions(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    prompt = await session.get(PromptTemplate, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    versions = (
        await session.scalars(
            select(PromptVersion)
            .where(PromptVersion.template_id == prompt_id)
            .order_by(PromptVersion.version.desc())
        )
    ).all()
    return [
        {
            "id": item.id,
            "version": item.version,
            "content": item.content,
            "variables": item.variables,
            "model_role": item.model_role,
            "is_active": item.is_active,
            "created_at": item.created_at,
        }
        for item in versions
    ]

