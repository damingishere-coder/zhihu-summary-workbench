from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from backend.app.core.config import REPOSITORY_ROOT, get_settings


_engines: dict[str, AsyncEngine] = {}
_session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}


def _normalize_database_url(database_url: str) -> str:
    prefix = "sqlite+aiosqlite:///./"
    if database_url.startswith(prefix):
        relative = database_url.removeprefix(prefix)
        target = (REPOSITORY_ROOT / relative).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{target.as_posix()}"
    return database_url


def get_engine(database_url: str | None = None) -> AsyncEngine:
    url = _normalize_database_url(database_url or get_settings().database_url)
    if url not in _engines:
        kwargs: dict[str, object] = {"pool_pre_ping": True}
        if url == "sqlite+aiosqlite:///:memory:":
            kwargs["poolclass"] = StaticPool
        _engines[url] = create_async_engine(url, **kwargs)
    return _engines[url]


def get_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    url = _normalize_database_url(database_url or get_settings().database_url)
    if url not in _session_factories:
        _session_factories[url] = async_sessionmaker(
            get_engine(url),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factories[url]


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engines() -> None:
    for engine in _engines.values():
        await engine.dispose()
    _engines.clear()
    _session_factories.clear()


def to_sync_database_url(database_url: str) -> str:
    normalized = _normalize_database_url(database_url)
    return normalized.replace("sqlite+aiosqlite", "sqlite").replace(
        "postgresql+asyncpg", "postgresql+psycopg"
    )

