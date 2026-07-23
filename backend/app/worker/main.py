from __future__ import annotations

import asyncio
import logging
import os
import socket

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.db.session import dispose_engines, get_session_factory
from backend.app.services.queue import create_queue_broker
from backend.app.services.tasks import process_task


logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    broker = create_queue_broker(settings.queue_backend, settings.redis_url)
    session_factory = get_session_factory()
    logger.info("Worker %s 已启动", worker_id)
    try:
        while True:
            await broker.heartbeat(worker_id, state="idle")
            task_id = await broker.dequeue(timeout=5)
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
        await broker.close()
        await dispose_engines()


def main() -> None:
    configure_logging()
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker 已停止")


if __name__ == "__main__":
    main()

