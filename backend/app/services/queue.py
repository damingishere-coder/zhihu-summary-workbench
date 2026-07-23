from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from backend.app.schemas.task import QueueStatus, WorkerRead


QUEUE_KEY = "zhihu-summary:tasks"
EVENT_CHANNEL = "zhihu-summary:events"
WORKER_HASH = "zhihu-summary:workers"


class QueueBroker(ABC):
    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def enqueue(self, task_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def dequeue(self, timeout: int = 5) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def publish(self, event: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def events(self) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def status(self) -> QueueStatus:
        raise NotImplementedError

    @abstractmethod
    async def heartbeat(
        self, worker_id: str, *, state: str, current_task_id: str | None = None
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def workers(self) -> list[WorkerRead]:
        raise NotImplementedError


class RedisQueueBroker(QueueBroker):
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client = redis.from_url(redis_url, decode_responses=True)

    async def close(self) -> None:
        await self.client.aclose()

    async def enqueue(self, task_id: str) -> None:
        await self.client.rpush(QUEUE_KEY, task_id)
        await self.publish({"type": "task_queued", "task_id": task_id})

    async def dequeue(self, timeout: int = 5) -> str | None:
        result = await self.client.blpop(QUEUE_KEY, timeout=timeout)
        return result[1] if result else None

    async def publish(self, event: dict[str, Any]) -> None:
        payload = {
            **event,
            "emitted_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.client.publish(EVENT_CHANNEL, json.dumps(payload, ensure_ascii=False))

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        pubsub = self.client.pubsub()
        await pubsub.subscribe(EVENT_CHANNEL)
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15
                )
                if message and message.get("data"):
                    yield json.loads(message["data"])
                else:
                    yield {
                        "type": "heartbeat",
                        "emitted_at": datetime.now(timezone.utc).isoformat(),
                    }
        finally:
            await pubsub.unsubscribe(EVENT_CHANNEL)
            await pubsub.aclose()

    async def status(self) -> QueueStatus:
        started = time.perf_counter()
        try:
            await self.client.ping()
            queued = int(await self.client.llen(QUEUE_KEY))
            return QueueStatus(
                connected=True,
                backend="redis",
                queued=queued,
                channel=EVENT_CHANNEL,
                latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
            )
        except Exception as exc:
            return QueueStatus(
                connected=False,
                backend="redis",
                queued=0,
                channel=EVENT_CHANNEL,
                error=str(exc),
            )

    async def heartbeat(
        self, worker_id: str, *, state: str, current_task_id: str | None = None
    ) -> None:
        payload = {
            "worker_id": worker_id,
            "state": state,
            "current_task_id": current_task_id,
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.client.hset(
            WORKER_HASH, worker_id, json.dumps(payload, ensure_ascii=False)
        )
        await self.client.expire(WORKER_HASH, 120)
        await self.publish({"type": "worker_heartbeat", **payload})

    async def workers(self) -> list[WorkerRead]:
        now = datetime.now(timezone.utc)
        values = await self.client.hvals(WORKER_HASH)
        workers: list[WorkerRead] = []
        for value in values:
            payload = json.loads(value)
            heartbeat_at = datetime.fromisoformat(payload["heartbeat_at"])
            workers.append(
                WorkerRead(
                    worker_id=payload["worker_id"],
                    state=payload["state"],
                    current_task_id=payload.get("current_task_id"),
                    heartbeat_at=heartbeat_at,
                    stale=(now - heartbeat_at).total_seconds() > 30,
                )
            )
        return sorted(workers, key=lambda item: item.worker_id)


class MemoryQueueBroker(QueueBroker):
    """测试用内存 Broker；生产默认始终使用 Redis。"""

    def __init__(self):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self.worker_state: dict[str, WorkerRead] = {}

    async def close(self) -> None:
        self.subscribers.clear()

    async def enqueue(self, task_id: str) -> None:
        await self.queue.put(task_id)
        await self.publish({"type": "task_queued", "task_id": task_id})

    async def dequeue(self, timeout: int = 5) -> str | None:
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def publish(self, event: dict[str, Any]) -> None:
        payload = {
            **event,
            "emitted_at": datetime.now(timezone.utc).isoformat(),
        }
        for subscriber in list(self.subscribers):
            await subscriber.put(payload)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        subscriber: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.subscribers.append(subscriber)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(subscriber.get(), timeout=15)
                except TimeoutError:
                    yield {
                        "type": "heartbeat",
                        "emitted_at": datetime.now(timezone.utc).isoformat(),
                    }
        finally:
            self.subscribers.remove(subscriber)

    async def status(self) -> QueueStatus:
        return QueueStatus(
            connected=True,
            backend="memory",
            queued=self.queue.qsize(),
            channel=EVENT_CHANNEL,
            latency_ms=0,
        )

    async def heartbeat(
        self, worker_id: str, *, state: str, current_task_id: str | None = None
    ) -> None:
        item = WorkerRead(
            worker_id=worker_id,
            state=state,
            current_task_id=current_task_id,
            heartbeat_at=datetime.now(timezone.utc),
        )
        self.worker_state[worker_id] = item
        await self.publish({"type": "worker_heartbeat", **item.model_dump(mode="json")})

    async def workers(self) -> list[WorkerRead]:
        return list(self.worker_state.values())


def create_queue_broker(backend: str, redis_url: str) -> QueueBroker:
    if backend == "memory":
        return MemoryQueueBroker()
    return RedisQueueBroker(redis_url)

