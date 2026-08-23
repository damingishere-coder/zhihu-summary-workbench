from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_broker
from backend.app.db.session import get_db_session
from backend.app.services.queue import QueueBroker
from backend.app.core.config import Settings, get_settings
from backend.app.models.browser_bridge import BrowserBridgeClient, CollectionJob
from backend.app.models.core import ModelUsageLog, SystemSetting
from backend.app.services.browser_bridge import bridge_manager
from backend.app.services.settings import public_settings


router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    database = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    queue = await broker.status()
    try:
        revision = await session.scalar(
            text("SELECT version_num FROM alembic_version LIMIT 1")
        )
    except Exception:
        await session.rollback()
        revision = "unversioned"
    client = await session.scalar(
        select(BrowserBridgeClient)
        .where(
            BrowserBridgeClient.status == "paired",
            BrowserBridgeClient.revoked_at.is_(None),
        )
        .order_by(BrowserBridgeClient.last_seen_at.desc())
        .limit(1)
    )
    active_job_id = await session.scalar(
        select(CollectionJob.id)
        .where(CollectionJob.status.in_(["pending", "dispatched"]))
        .order_by(CollectionJob.created_at)
        .limit(1)
    )
    public = await public_settings(session, settings)
    provider_configured = (
        public.codex_configured
        if public.provider_mode == "codex"
        else public.deepseek_configured
        if public.provider_mode == "deepseek"
        else True
    )
    validation = await session.get(SystemSetting, "model_last_real_validation")
    latest_real_usage = await session.scalar(
        select(ModelUsageLog)
        .where(
            ModelUsageLog.provider != "mock",
            ModelUsageLog.status == "success",
            ModelUsageLog.cache_hit.is_(False),
        )
        .order_by(ModelUsageLog.created_at.desc())
        .limit(1)
    )
    last_real_validation = (
        {
            "provider": latest_real_usage.provider,
            "model": latest_real_usage.model,
            "stage": latest_real_usage.stage,
            "verified_at": latest_real_usage.created_at.isoformat(),
        }
        if latest_real_usage
        else validation.value
        if validation
        else None
    )
    connected = bool(client and client.id in bridge_manager.connected_client_ids)
    auth = client.zhihu_auth if client else "unknown"
    capability = (
        "ready"
        if connected and auth == "authenticated"
        else "waiting_login"
        if connected and auth == "login_required"
        else "waiting_verification"
        if connected and auth == "verification_required"
        else "waiting_extension"
    )
    return {
        "status": "ok" if database == "ok" and queue.connected else "degraded",
        "app_id": settings.app_id,
        "database": database,
        "database_revision": revision,
        "redis": "ok" if queue.connected else "error",
        "queue_backend": queue.backend,
        "browser_bridge": {
            "connection": "connected" if connected else "disconnected" if client else "unpaired",
            "zhihu_auth": auth,
            "collection_capability": capability,
            "active_job_id": active_job_id,
            "last_seen_at": client.last_seen_at.isoformat() if client and client.last_seen_at else None,
        },
        "model": {
            "provider_mode": public.provider_mode,
            "configured": provider_configured,
            "last_real_validation": last_real_validation,
        },
    }
