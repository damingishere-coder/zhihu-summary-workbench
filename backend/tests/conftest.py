from __future__ import annotations

import os

import httpx
import pytest_asyncio

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["QUEUE_BACKEND"] = "memory"
os.environ["AI_PROVIDER_MODE"] = "mock"
os.environ["DEEPSEEK_API_KEY"] = ""

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.session import get_engine, get_session_factory
from backend.app.main import create_app
from backend.app.services.queue import MemoryQueueBroker
from backend.app.services.seed import seed_defaults


@pytest_asyncio.fixture
async def app_client():
    get_settings.cache_clear()
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with get_session_factory()() as session:
        await seed_defaults(session)

    app = create_app()
    broker = MemoryQueueBroker()
    app.state.broker = broker
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield app, client, broker

    await broker.close()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
