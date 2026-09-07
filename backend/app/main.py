from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.db.session import dispose_engines, get_session_factory
from backend.app.services.queue import create_queue_broker
from backend.app.services.seed import seed_defaults
from backend.app.services.checkpoints import recover_interrupted_tasks
from backend.app.services.browser_bridge import run_bridge_dispatch_loop
from backend.app.worker.main import run_worker_loop


configure_logging()

EMBEDDED_WORKER_SHUTDOWN_TIMEOUT_SECONDS = 5


async def _stop_embedded_worker(app: FastAPI) -> None:
    stop_event = getattr(app.state, "worker_stop_event", None)
    worker_task = getattr(app.state, "worker_task", None)
    if stop_event is None or worker_task is None or worker_task.done():
        return

    stop_event.set()
    try:
        await asyncio.wait_for(
            asyncio.shield(worker_task),
            timeout=EMBEDDED_WORKER_SHUTDOWN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task


async def _stop_bridge_dispatcher(app: FastAPI) -> None:
    stop_event = getattr(app.state, "bridge_stop_event", None)
    task = getattr(app.state, "bridge_dispatch_task", None)
    if stop_event is None or task is None or task.done():
        return
    stop_event.set()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=3)
    except asyncio.TimeoutError:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    broker = create_queue_broker(settings.queue_backend, settings.redis_url)
    app.state.broker = broker
    app.state.worker_task = None
    app.state.worker_stop_event = None
    app.state.bridge_stop_event = asyncio.Event()
    app.state.bridge_dispatch_task = None
    try:
        async with get_session_factory()() as session:
            await seed_defaults(session)
            await recover_interrupted_tasks(session)
        app.state.bridge_dispatch_task = asyncio.create_task(
            run_bridge_dispatch_loop(
                stop_event=app.state.bridge_stop_event,
                session_factory=get_session_factory(),
            ),
            name="browser-bridge-dispatcher",
        )
        if settings.queue_backend == "memory":
            stop_event = asyncio.Event()
            app.state.worker_stop_event = stop_event
            app.state.worker_task = asyncio.create_task(
                run_worker_loop(
                    broker,
                    settings=settings,
                    stop_event=stop_event,
                    session_factory=get_session_factory(),
                    owns_broker=False,
                    owns_database=False,
                ),
                name="embedded-memory-worker",
            )
        yield
    finally:
        try:
            await _stop_embedded_worker(app)
        finally:
            try:
                await _stop_bridge_dispatcher(app)
            finally:
                try:
                    await broker.close()
                finally:
                    await dispose_engines()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.4.0",
        description="知乎问题总结工作台 Chrome 扩展桥接 API",
        lifespan=lifespan,
    )
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
