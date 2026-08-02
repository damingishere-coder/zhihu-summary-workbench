from __future__ import annotations

from fastapi import Request

from backend.app.services.queue import QueueBroker


def get_broker(request: Request) -> QueueBroker:
    return request.app.state.broker

