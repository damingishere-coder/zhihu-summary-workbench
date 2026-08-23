from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import backend.app.main as app_main
import backend.app.worker.main as worker_main
from backend.app.services.queue import MemoryQueueBroker


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: Any) -> None:
        return None


def _session_factory() -> _SessionContext:
    return _SessionContext()


class _CountingBroker(MemoryQueueBroker):
    def __init__(self) -> None:
        super().__init__()
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1
        await super().close()


class _BlockingBroker(_CountingBroker):
    def __init__(self) -> None:
        super().__init__()
        self.dequeue_started = asyncio.Event()
        self.dequeue_cancelled = asyncio.Event()
        self._blocker = asyncio.Event()

    async def dequeue(self, timeout: int = 5) -> str | None:
        del timeout
        self.dequeue_started.set()
        try:
            await self._blocker.wait()
        except asyncio.CancelledError:
            self.dequeue_cancelled.set()
            raise
        return None


@pytest.mark.asyncio
async def test_memory_worker_consumes_from_the_api_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processed = asyncio.Event()

    async def fake_daily_plan(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def fake_process_task(*_args: Any, **_kwargs: Any) -> None:
        processed.set()

    monkeypatch.setattr(worker_main, "run_due_daily_plan", fake_daily_plan)
    monkeypatch.setattr(worker_main, "process_task", fake_process_task)

    broker = _CountingBroker()
    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(
        worker_main.run_worker_loop(
            broker,
            settings=SimpleNamespace(),
            stop_event=stop_event,
            session_factory=_session_factory,
            owns_broker=False,
            owns_database=False,
            worker_id="test-memory-worker",
        )
    )

    await broker.enqueue("task-1")
    await asyncio.wait_for(processed.wait(), timeout=1)
    assert broker.queue.qsize() == 0
    assert (await broker.workers())[0].worker_id == "test-memory-worker"

    stop_event.set()
    await asyncio.wait_for(worker_task, timeout=1)
    assert worker_task.done()
    assert broker.close_count == 0

    await broker.close()


@pytest.mark.asyncio
async def test_embedded_worker_uses_shared_broker_and_stops_on_memory_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _CountingBroker()
    embedded_started = asyncio.Event()
    observed: dict[str, Any] = {}
    dispose_count = 0

    async def fake_embedded_worker(broker_arg: Any, **kwargs: Any) -> None:
        observed["broker"] = broker_arg
        observed.update(kwargs)
        embedded_started.set()
        await kwargs["stop_event"].wait()

    async def fake_seed_defaults(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def fake_dispose_engines() -> None:
        nonlocal dispose_count
        dispose_count += 1

    settings = SimpleNamespace(
        app_name="test",
        api_prefix="/api",
        cors_origins=[],
        queue_backend="memory",
        redis_url="redis://unused",
    )
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(app_main, "create_queue_broker", lambda *_args: broker)
    monkeypatch.setattr(app_main, "get_session_factory", lambda: _session_factory)
    monkeypatch.setattr(app_main, "seed_defaults", fake_seed_defaults)
    monkeypatch.setattr(app_main, "dispose_engines", fake_dispose_engines)
    monkeypatch.setattr(app_main, "run_worker_loop", fake_embedded_worker)

    app = app_main.create_app()
    async with app_main.lifespan(app):
        await asyncio.wait_for(embedded_started.wait(), timeout=1)
        assert observed["broker"] is broker
        assert observed["owns_broker"] is False
        assert observed["owns_database"] is False
        assert app.state.worker_task is not None
        assert not app.state.worker_task.done()

    assert app.state.worker_task.done()
    assert broker.close_count == 1
    assert dispose_count == 1


@pytest.mark.asyncio
async def test_redis_lifespan_does_not_start_an_embedded_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _CountingBroker()
    embedded_started = asyncio.Event()
    dispose_count = 0

    async def fake_embedded_worker(*_args: Any, **_kwargs: Any) -> None:
        embedded_started.set()

    async def fake_seed_defaults(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def fake_dispose_engines() -> None:
        nonlocal dispose_count
        dispose_count += 1

    settings = SimpleNamespace(
        app_name="test",
        api_prefix="/api",
        cors_origins=[],
        queue_backend="redis",
        redis_url="redis://unused",
    )
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(app_main, "create_queue_broker", lambda *_args: broker)
    monkeypatch.setattr(app_main, "get_session_factory", lambda: _session_factory)
    monkeypatch.setattr(app_main, "seed_defaults", fake_seed_defaults)
    monkeypatch.setattr(app_main, "dispose_engines", fake_dispose_engines)
    monkeypatch.setattr(app_main, "run_worker_loop", fake_embedded_worker)

    app = app_main.create_app()
    async with app_main.lifespan(app):
        await asyncio.sleep(0)
        assert app.state.worker_task is None
        assert not embedded_started.is_set()

    assert broker.close_count == 1
    assert dispose_count == 1


@pytest.mark.asyncio
async def test_worker_owns_resources_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _CountingBroker()
    dispose_count = 0

    async def fake_dispose_engines() -> None:
        nonlocal dispose_count
        dispose_count += 1

    monkeypatch.setattr(worker_main, "dispose_engines", fake_dispose_engines)
    stop_event = asyncio.Event()
    stop_event.set()

    await worker_main.run_worker_loop(
        broker,
        settings=SimpleNamespace(),
        stop_event=stop_event,
        session_factory=_session_factory,
        owns_broker=True,
        owns_database=True,
        worker_id="standalone-test-worker",
    )

    assert broker.close_count == 1
    assert dispose_count == 1


@pytest.mark.asyncio
async def test_worker_cancellation_cleans_up_dequeue_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_daily_plan(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(worker_main, "run_due_daily_plan", fake_daily_plan)
    broker = _BlockingBroker()
    worker_task = asyncio.create_task(
        worker_main.run_worker_loop(
            broker,
            settings=SimpleNamespace(),
            stop_event=asyncio.Event(),
            session_factory=_session_factory,
            owns_broker=False,
            owns_database=False,
            worker_id="cancel-test-worker",
        )
    )

    await asyncio.wait_for(broker.dequeue_started.wait(), timeout=1)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task
    assert broker.dequeue_cancelled.is_set()
    assert broker.close_count == 0


async def _noop() -> None:
    return None
