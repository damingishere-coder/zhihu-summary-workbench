from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.db.session import dispose_engines, get_session_factory
from backend.app.services.queue import create_queue_broker
from backend.app.services.seed import seed_defaults
from backend.app.services.browser_session import ManagedZhihuBrowserSession


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    broker = create_queue_broker(settings.queue_backend, settings.redis_url)
    app.state.broker = broker
    async with get_session_factory()() as session:
        await seed_defaults(session)
    yield
    await app.state.zhihu_browser_session.shutdown()
    await broker.close()
    await dispose_engines()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.3.0",
        description="知乎问题总结工作台第三阶段 API",
        lifespan=lifespan,
    )
    app.state.zhihu_browser_session = ManagedZhihuBrowserSession()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
