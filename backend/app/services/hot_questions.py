"""Hot-list requests use the paired user's ordinary Chrome page."""
from __future__ import annotations

import asyncio
import secrets
from typing import Any

from sqlalchemy import select
from pydantic import BaseModel, Field

from backend.app.models.core import Question
from backend.app.schemas.question import QuestionCreate
from backend.app.services.questions import create_question


class HotEntry(BaseModel):
    id: str = Field(pattern=r"^\d{1,32}$")
    title: str = Field(min_length=1, max_length=500)
    rank: int = Field(ge=1, le=100)


pending: dict[str, tuple[str, asyncio.Future]] = {}


def receive_hot_result(client_id: str, nonce: str, payload: dict[str, Any]) -> None:
    item = pending.get(nonce)
    if item and secrets.compare_digest(item[0], client_id) and not item[1].done():
        item[1].set_result(payload)


async def sync_hot_questions(session, *, limit: int = 30) -> dict[str, Any]:
    from backend.app.services.browser_bridge import bridge_manager
    from backend.app.schemas.browser_bridge import PROTOCOL_VERSION
    clients = bridge_manager.connected_client_ids
    if not clients:
        return {"fetched": 0, "created": 0, "updated": 0, "collector_mode": "chrome_extension", "warnings": ["扩展未连接，使用已有候选问题；请先连接扩展后重试热榜"]}
    client_id = next(iter(clients))
    nonce = secrets.token_hex(16)
    future = asyncio.get_running_loop().create_future()
    pending[nonce] = (client_id, future)
    try:
        sent = await bridge_manager.send_control(client_id, {"type": "collect_hot", "protocol_version": PROTOCOL_VERSION, "nonce": nonce, "job_id": nonce, "limit": limit})
        if not sent:
            raise RuntimeError("扩展连接已中断")
        payload = await asyncio.wait_for(future, timeout=90)
        if payload.get("error"):
            raise ValueError(str(payload["error"])[:500])
        raw = payload.get("items", [])
        if not isinstance(raw, list) or len(raw) > 100:
            raise ValueError("热榜返回格式无效")
        entries = [HotEntry.model_validate(row) for row in raw]
        created = updated = 0
        seen: set[str] = set()
        for entry in entries[:limit]:
            if entry.id in seen:
                continue
            seen.add(entry.id)
            url = f"https://www.zhihu.com/question/{entry.id}"
            question = await session.scalar(select(Question).where(Question.url == url))
            if question is None:
                question = await create_question(session, QuestionCreate(url=url, title=entry.title), source="hot")
                created += 1
            else:
                updated += 1
            question.title = entry.title
            question.hot_rank = entry.rank
            from backend.app.models.common import utc_now
            question.fetched_at = utc_now()
        await session.commit()
        return {"fetched": len(seen), "created": created, "updated": updated, "collector_mode": "chrome_extension", "warnings": []}
    except (TimeoutError, ValueError, RuntimeError) as exc:
        return {"fetched": 0, "created": 0, "updated": 0, "collector_mode": "chrome_extension", "warnings": [str(exc) or "热榜采集超时，使用已有候选"]}
    finally:
        pending.pop(nonce, None)
