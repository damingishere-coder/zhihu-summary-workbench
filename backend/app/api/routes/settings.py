from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from backend.app.ai.providers.base import ProviderError
from backend.app.ai.providers.factory import create_structured_provider
from backend.app.ai.services.claim_extractor import ClaimExtractionService
from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_db_session
from backend.app.schemas.ai import ModelUsage
from backend.app.schemas.settings import (
    ModelTestRequest,
    ModelTestResponse,
    PublicSettings,
    SettingsUpdate,
)
from backend.app.models.core import SystemSetting
from backend.app.services.settings import (
    configured_settings_copy,
    public_settings,
    update_public_settings,
)


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=PublicSettings)
async def get_public_settings(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PublicSettings:
    return await public_settings(session, settings)


@router.patch("", response_model=PublicSettings)
async def patch_public_settings(
    payload: SettingsUpdate,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PublicSettings:
    try:
        return await update_public_settings(session, payload, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-model", response_model=ModelTestResponse)
async def test_model(
    payload: ModelTestRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ModelTestResponse:
    runtime_settings = await configured_settings_copy(session, settings)
    mode = payload.provider_mode or (
        await public_settings(session, settings)
    ).provider_mode
    try:
        provider = create_structured_provider(mode, runtime_settings)
        result = await ClaimExtractionService(provider).extract(
            question_title=payload.question_title,
            answer_text=payload.sample_answer,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    usage = result.usage
    if mode != "mock":
        item = await session.get(SystemSetting, "model_last_real_validation")
        value = {
            "provider": usage.provider,
            "model": usage.model,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        if item:
            item.value = value
        else:
            session.add(
                SystemSetting(
                    key="model_last_real_validation",
                    value=value,
                    is_secret=False,
                )
            )
        await session.commit()
    return ModelTestResponse(
        success=True,
        provider=usage.provider,
        model=usage.model,
        message="结构化输出校验通过",
        analysis=result.data,
        usage=ModelUsage(
            provider=usage.provider,
            model=usage.model,
            model_role=usage.model_role,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            duration_ms=usage.duration_ms,
            estimated_cost=usage.estimated_cost,
        ),
    )
