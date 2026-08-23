from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers.codex import CodexProvider
from backend.app.core.config import Settings
from backend.app.models.core import SystemSetting
from backend.app.schemas.settings import PublicSettings, SettingsUpdate


SETTING_DEFAULTS: dict[str, object] = {
    # 默认改用本机 Codex；自动生产和自动发布仍为关闭，不会因启动服务自行消耗额度。
    "provider_mode": "codex",
    "codex_model": "gpt-5.6-sol",
    "daily_question_limit": 10,
    "hot_question_quota": 6,
    "manual_question_quota": 4,
    "max_answers_per_question": 100,
    "max_ai_concurrency": 3,
    "request_timeout_seconds": 60,
    "daily_plan_time": "09:00",
    "daily_publish_limit": 10,
    "publish_interval_minutes": 30,
    "auto_production_enabled": False,
    "auto_publish_enabled": False,
    "daily_model_budget": 0,
    "pause_on_budget_exceeded": True,
    "response_cache_enabled": True,
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
    codex_status = CodexProvider.status(settings)
    return PublicSettings(
        provider_mode=await provider_mode(session, settings),
        codex_configured=bool(codex_status["ok"]),
        codex_model=str(
            await get_setting(session, "codex_model", settings.codex_model)
        ),
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
        hot_question_quota=int(
            await get_setting(
                session, "hot_question_quota", settings.hot_question_quota
            )
        ),
        manual_question_quota=int(
            await get_setting(
                session, "manual_question_quota", settings.manual_question_quota
            )
        ),
        max_answers_per_question=int(
            await get_setting(
                session,
                "max_answers_per_question",
                settings.max_answers_per_question,
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
        daily_plan_time=str(
            await get_setting(session, "daily_plan_time", settings.daily_plan_time)
        ),
        daily_publish_limit=int(
            await get_setting(
                session, "daily_publish_limit", settings.daily_publish_limit
            )
        ),
        publish_interval_minutes=int(
            await get_setting(
                session,
                "publish_interval_minutes",
                settings.publish_interval_minutes,
            )
        ),
        auto_production_enabled=bool(
            await get_setting(
                session,
                "auto_production_enabled",
                settings.auto_production_enabled,
            )
        ),
        auto_publish_enabled=bool(
            await get_setting(
                session,
                "auto_publish_enabled",
                settings.auto_publish_enabled,
            )
        ),
        daily_model_budget=float(
            await get_setting(
                session, "daily_model_budget", settings.daily_model_budget
            )
        ),
        pause_on_budget_exceeded=bool(
            await get_setting(
                session,
                "pause_on_budget_exceeded",
                settings.pause_on_budget_exceeded,
            )
        ),
        response_cache_enabled=bool(
            await get_setting(
                session,
                "response_cache_enabled",
                settings.response_cache_enabled,
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
    if values.get("provider_mode") == "codex" and not CodexProvider.status(settings)["ok"]:
        raise ValueError("Codex 模式需要安装 Codex CLI 并登录当前 ChatGPT 账号")
    current = await public_settings(session, settings)
    quota_keys = {
        "daily_question_limit",
        "hot_question_quota",
        "manual_question_quota",
    }
    if quota_keys.intersection(values):
        question_limit = int(
            values.get("daily_question_limit", current.daily_question_limit)
        )
        hot_quota = int(values.get("hot_question_quota", current.hot_question_quota))
        manual_quota = int(
            values.get("manual_question_quota", current.manual_question_quota)
        )
        if hot_quota + manual_quota > question_limit:
            raise ValueError("热门配额与手动配额之和不能超过每日问题数")
    auto_production = bool(
        values.get("auto_production_enabled", current.auto_production_enabled)
    )
    auto_publish = bool(
        values.get("auto_publish_enabled", current.auto_publish_enabled)
    )
    if auto_publish and not auto_production:
        raise ValueError("开启自动发布前必须先开启自动生产")
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
            "codex_model": current.codex_model,
            "codex_timeout_seconds": current.request_timeout_seconds,
            "deepseek_fast_model": current.fast_text_model,
            "deepseek_reasoning_model": current.reasoning_model,
            "deepseek_fallback_model": current.fallback_text_model,
            "embedding_model": current.embedding_model,
            "ai_request_timeout_seconds": current.request_timeout_seconds,
            "zhihu_browser_user_data_dir": current.browser_user_data_dir,
            "max_answers_per_question": current.max_answers_per_question,
            "max_ai_concurrency": current.max_ai_concurrency,
            "daily_question_limit": current.daily_question_limit,
            "hot_question_quota": current.hot_question_quota,
            "manual_question_quota": current.manual_question_quota,
            "daily_plan_time": current.daily_plan_time,
            "daily_publish_limit": current.daily_publish_limit,
            "publish_interval_minutes": current.publish_interval_minutes,
            "auto_production_enabled": current.auto_production_enabled,
            "auto_publish_enabled": current.auto_publish_enabled,
            "daily_model_budget": current.daily_model_budget,
            "pause_on_budget_exceeded": current.pause_on_budget_exceeded,
            "response_cache_enabled": current.response_cache_enabled,
        }
    )
