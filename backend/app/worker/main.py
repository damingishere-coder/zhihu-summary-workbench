from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Callable
from typing import Any

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.db.session import dispose_engines, get_session_factory
from backend.app.services.queue import QueueBroker, create_queue_broker
from backend.app.services.daily_plan import run_due_daily_plan
from backend.app.services.tasks import process_task


logger = logging.getLogger(__name__)


async def _dequeue_until_stopped(
    broker: QueueBroker,
    stop_event: asyncio.Event,
    *,
    timeout: int = 5,
) -> str | None:
    """Wait for a task while allowing an embedded worker to stop promptly."""

    if stop_event.is_set():
        return None

    dequeue_task = asyncio.create_task(broker.dequeue(timeout=timeout))
    stop_task = asyncio.create_task(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            {dequeue_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            return None
        return dequeue_task.result()
    finally:
        for pending_task in (dequeue_task, stop_task):
            if not pending_task.done():
                pending_task.cancel()
        await asyncio.gather(
            dequeue_task,
            stop_task,
            return_exceptions=True,
        )


async def run_worker_loop(
    broker: QueueBroker,
    *,
    settings: Any | None = None,
    stop_event: asyncio.Event | None = None,
    session_factory: Callable[[], Any] | None = None,
    owns_broker: bool = False,
    owns_database: bool = False,
    worker_id: str | None = None,
) -> None:
    """Run the task loop with explicit resource ownership.

    The standalone Worker owns the Broker and database engines.  An embedded
    memory Worker receives the API's Broker and session factory, so it must not
    dispose either resource during shutdown.
    """

    settings = settings or get_settings()
    stop_event = stop_event or asyncio.Event()
    session_factory = session_factory or get_session_factory()
    worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
    logger.info("Worker %s 已启动", worker_id)
    try:
        while not stop_event.is_set():
            await broker.heartbeat(worker_id, state="idle")
            async with session_factory() as session:
                try:
                    result = await run_due_daily_plan(
                        session, broker, settings
                    )
                    if result:
                        logger.info(result.message)
                except Exception:
                    logger.exception("检查每日定时计划失败，将在下一轮重试")
            task_id = await _dequeue_until_stopped(broker, stop_event)
            if not task_id:
                continue
            await broker.heartbeat(
                worker_id, state="busy", current_task_id=task_id
            )
            await process_task(
                task_id,
                worker_id=worker_id,
                settings=settings,
                broker=broker,
                session_factory=session_factory,
            )
    finally:
        if owns_broker:
            await broker.close()
        if owns_database:
            await dispose_engines()


async def run_worker() -> None:
    settings = get_settings()
    broker = create_queue_broker(settings.queue_backend, settings.redis_url)
    await run_worker_loop(
        broker,
        settings=settings,
        owns_broker=True,
        owns_database=True,
    )


def main() -> None:
    configure_logging()
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker 已停止")


if __name__ == "__main__":
    main()
