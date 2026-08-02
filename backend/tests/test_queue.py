import asyncio

import pytest

from backend.app.services.queue import MemoryQueueBroker


@pytest.mark.asyncio
async def test_memory_queue_publishes_sse_compatible_event() -> None:
    broker = MemoryQueueBroker()
    stream = broker.events()
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    await broker.publish({"type": "task_progress", "progress": 35})
    event = await asyncio.wait_for(pending, timeout=1)
    assert event["type"] == "task_progress"
    assert event["progress"] == 35
    assert "emitted_at" in event
    await stream.aclose()

