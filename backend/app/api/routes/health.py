from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_broker
from backend.app.db.session import get_db_session
from backend.app.services.queue import QueueBroker


router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
) -> dict[str, object]:
    database = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    queue = await broker.status()
    return {
        "status": "ok" if database == "ok" and queue.connected else "degraded",
        "database": database,
        "redis": "ok" if queue.connected else "error",
        "queue_backend": queue.backend,
    }
