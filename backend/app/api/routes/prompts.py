from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers.base import ProviderError
from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_db_session
from backend.app.models.core import PromptTemplate
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
from backend.app.services.prompts import (
    activate_prompt_version,
    create_prompt,
    create_prompt_version,
    list_prompt_templates,
    list_prompt_versions,
    prompt_audits,
    test_prompt,
)


router = APIRouter(prefix="/prompts", tags=["prompts"])


async def _template(
    session: AsyncSession, prompt_id: str
) -> PromptTemplate:
    item = await session.get(PromptTemplate, prompt_id)
    if not item:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    return item


@router.get("", response_model=list[PromptTemplateRead])
async def list_prompts(
    session: AsyncSession = Depends(get_db_session),
) -> list[PromptTemplateRead]:
    return await list_prompt_templates(session)


@router.post("", response_model=PromptTemplateRead, status_code=201)
async def post_prompt(
    payload: PromptCreate,
    session: AsyncSession = Depends(get_db_session),
) -> PromptTemplateRead:
    try:
        return await create_prompt(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{prompt_id}", response_model=PromptVersionRead)
async def patch_prompt(
    prompt_id: str,
    payload: PromptUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> PromptVersionRead:
    template = await _template(session, prompt_id)
    return await create_prompt_version(session, template, payload)


@router.post(
    "/{prompt_id}/activate", response_model=PromptTemplateRead
)
async def activate_prompt(
    prompt_id: str,
    payload: PromptActivateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PromptTemplateRead:
    template = await _template(session, prompt_id)
    try:
        return await activate_prompt_version(session, template, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{prompt_id}/test", response_model=PromptTestResponse)
async def run_prompt_test(
    prompt_id: str,
    payload: PromptTestRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PromptTestResponse:
    template = await _template(session, prompt_id)
    try:
        return await test_prompt(session, template, payload, settings)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/{prompt_id}/versions", response_model=list[PromptVersionRead]
)
async def get_prompt_versions(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[PromptVersionRead]:
    await _template(session, prompt_id)
    return await list_prompt_versions(session, prompt_id)


@router.get(
    "/{prompt_id}/audits", response_model=list[PromptAuditRead]
)
async def get_prompt_audits(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[PromptAuditRead]:
    await _template(session, prompt_id)
    return await prompt_audits(session, prompt_id)
