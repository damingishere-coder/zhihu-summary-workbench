from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings
from backend.app.models.core import SystemSetting
from backend.app.schemas.settings import PublicSettings, SettingsUpdate


SETTING_DEFAULTS: dict[str, object] = {
    "provider_mode": "mock",
    "daily_question_limit": 10,
    "max_ai_concurrency": 3,
    "request_timeout_seconds": 60,
    "auto_publish_enabled": False,
}


async def get_setting(
    session: AsyncSession, key: str, default: object | None = None
) -> object | None:
    item = await session.get(SystemSetting, key)
    return item.value if item else default


async def set_setting(session: AsyncSession, key: str, value: object) -> None:
    item = await session.get(SystemSetting, key)
    if item:
        item.value = value
    else:
        session.add(SystemSetting(key=key, value=value, is_secret=False))


async def provider_mode(session: AsyncSession, settings: Settings) -> str:
    value = await get_setting(session, "provider_mode", settings.ai_provider_mode)
    return str(value)


def _display_redis_url(redis_url: str) -> str:
    parsed = urlsplit(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    path = parsed.path or "/0"
    return f"{parsed.scheme or 'redis'}://{host}:{port}{path}"


async def public_settings(
    session: AsyncSession, settings: Settings
) -> PublicSettings:
    return PublicSettings(
        provider_mode=await provider_mode(session, settings),
        deepseek_configured=bool(settings.deepseek_key_value),
        deepseek_base_url=settings.deepseek_base_url,
        fast_text_model=str(
            await get_setting(
                session, "fast_text_model", settings.deepseek_fast_model
            )
        ),
        reasoning_model=str(
            await get_setting(
                session, "reasoning_model", settings.deepseek_reasoning_model
            )
        ),
        fallback_text_model=str(
            await get_setting(
                session, "fallback_text_model", settings.deepseek_fallback_model
            )
        ),
        embedding_provider=settings.embedding_provider,
        embedding_model=str(
            await get_setting(session, "embedding_model", settings.embedding_model)
        ),
        image_generation_mode=settings.image_generation_mode,
        allow_manual_image_upload=settings.allow_manual_image_upload,
        daily_question_limit=int(
            await get_setting(
                session, "daily_question_limit", settings.daily_question_limit
            )
        ),
        max_ai_concurrency=int(
            await get_setting(
                session, "max_ai_concurrency", settings.max_ai_concurrency
            )
        ),
        request_timeout_seconds=int(
            await get_setting(
                session,
                "request_timeout_seconds",
                settings.ai_request_timeout_seconds,
            )
        ),
        browser_user_data_dir=str(
            await get_setting(
                session,
                "browser_user_data_dir",
                settings.zhihu_browser_user_data_dir,
            )
        ),
        redis_url_display=_display_redis_url(settings.redis_url),
    )


async def update_public_settings(
    session: AsyncSession, payload: SettingsUpdate, settings: Settings
) -> PublicSettings:
    values = payload.model_dump(exclude_none=True)
    if values.get("provider_mode") == "deepseek" and not settings.deepseek_key_value:
        raise ValueError(
            "DeepSeek 模式需要在本机 .env 中配置 DEEPSEEK_API_KEY；密钥不会通过页面保存"
        )
    for key, value in values.items():
        await set_setting(session, key, value)
    await session.commit()
    return await public_settings(session, settings)


async def configured_settings_copy(
    session: AsyncSession, settings: Settings
) -> Settings:
    current = await public_settings(session, settings)
    return settings.model_copy(
        update={
            "deepseek_fast_model": current.fast_text_model,
            "deepseek_reasoning_model": current.reasoning_model,
            "deepseek_fallback_model": current.fallback_text_model,
            "embedding_model": current.embedding_model,
            "ai_request_timeout_seconds": current.request_timeout_seconds,
            "zhihu_browser_user_data_dir": current.browser_user_data_dir,
        }
    )
