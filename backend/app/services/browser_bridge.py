from __future__ import annotations

import asyncio
import hashlib
import html
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from fastapi import WebSocket
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.collectors.zhihu import (
    CollectedAnswer,
    CollectedQuestion,
    ZhihuFetchResult,
    basic_filter_reason,
    clean_answer_html,
)
from backend.app.models.browser_bridge import BrowserBridgeClient, CollectionJob
from backend.app.models.common import utc_now
from backend.app.models.core import Question, TaskJob, TaskLog
from backend.app.schemas.browser_bridge import ImportBundleV1, PROTOCOL_VERSION
from backend.app.services.queue import QueueBroker


PAIRING_TTL = timedelta(minutes=10)
PAIRING_ALPHABET = string.ascii_uppercase + string.digits
ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "ul",
}
ALLOWED_ATTRIBUTES = {"a": {"href"}, "img": {"src", "data-original", "alt"}}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _safe_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} or (not parsed.scheme and value.startswith("/")):
        return value
    return ""


class _SafeHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in ALLOWED_TAGS:
            return
        safe_attrs: list[str] = []
        for key, value in attrs:
            if key not in ALLOWED_ATTRIBUTES.get(tag, set()) or value is None:
                continue
            safe_value = _safe_url(value) if key in {"href", "src", "data-original"} else value
            if safe_value:
                safe_attrs.append(f'{key}="{html.escape(safe_value, quote=True)}"')
        attributes = f" {' '.join(safe_attrs)}" if safe_attrs else ""
        self.parts.append(f"<{tag}{attributes}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in ALLOWED_TAGS and tag not in {"br", "img"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.parts.append(html.escape(data))


def sanitize_zhihu_html(value: str) -> str:
    parser = _SafeHtmlParser()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts)


def bundle_to_fetch_result(
    bundle: ImportBundleV1, *, collector_mode: str
) -> ZhihuFetchResult:
    question_payload = bundle.question
    question = CollectedQuestion(
        external_id=question_payload.id,
        title=question_payload.title.strip(),
        url=f"https://www.zhihu.com/question/{question_payload.id}",
        description=clean_answer_html(
            sanitize_zhihu_html(question_payload.detail or question_payload.excerpt)
        )[0],
        answer_count=question_payload.answer_count,
        follower_count=question_payload.follower_count,
        raw_snapshot={
            "id": question_payload.id,
            "title": question_payload.title,
            "answer_count": question_payload.answer_count,
            "follower_count": question_payload.follower_count,
        },
    )
    answers: list[CollectedAnswer] = []
    for order, item in enumerate(bundle.answers):
        safe_html = sanitize_zhihu_html(item.content)
        plain, markdown, media = clean_answer_html(safe_html)
        answers.append(
            CollectedAnswer(
                external_id=item.id,
                author_name=item.author.name or "匿名用户",
                author_url=(
                    f"https://www.zhihu.com/people/{item.author.url_token}"
                    if item.author.url_token
                    else ""
                ),
                answer_url=f"https://www.zhihu.com/question/{item.question_id}/answer/{item.id}",
                html_content=safe_html,
                markdown_content=markdown,
                plain_content=plain,
                content_hash=hashlib.sha256(plain.encode("utf-8")).hexdigest(),
                vote_count=item.voteup_count,
                comment_count=item.comment_count,
                published_at=_from_timestamp(item.created_time),
                updated_at=_from_timestamp(item.updated_time),
                sort_order=order,
                media=media,
                raw_snapshot={
                    "id": item.id,
                    "question_id": item.question_id,
                    "author_name": item.author.name,
                    "voteup_count": item.voteup_count,
                    "comment_count": item.comment_count,
                    "created_time": item.created_time,
                    "updated_time": item.updated_time,
                },
                filter_reason=basic_filter_reason(plain),
            )
        )
    return ZhihuFetchResult(
        question=question,
        answers=answers,
        collector_mode=collector_mode,
        warnings=[item[:500] for item in bundle.warnings],
    )


def _from_timestamp(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


@dataclass(slots=True)
class PairingGrant:
    code: str
    expires_at: datetime


@dataclass(slots=True)
class ActiveConnection:
    client_id: str
    websocket: WebSocket


class BrowserBridgeManager:
    def __init__(self) -> None:
        self._pairings: dict[str, PairingGrant] = {}
        self._connections: dict[str, ActiveConnection] = {}
        self._lock = asyncio.Lock()

    @property
    def connected_client_ids(self) -> set[str]:
        return set(self._connections)

    def create_pairing(self) -> PairingGrant:
        now = utc_now()
        self._pairings = {
            key: item for key, item in self._pairings.items() if item.expires_at > now
        }
        while True:
            code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))
            if code not in self._pairings:
                break
        grant = PairingGrant(code=code, expires_at=now + PAIRING_TTL)
        self._pairings[code] = grant
        return grant

    async def authenticate_hello(
        self, session: AsyncSession, payload: dict[str, Any]
    ) -> tuple[BrowserBridgeClient, str | None]:
        if int(payload.get("protocol_version") or 0) != PROTOCOL_VERSION:
            raise ValueError("扩展协议版本不兼容")
        extension_version = str(payload.get("extension_version") or "")[:64]
        token = str(payload.get("token") or "")
        pairing_code = str(payload.get("pairing_code") or "").upper()
        issued_token: str | None = None
        client: BrowserBridgeClient | None = None
        if token:
            client = await session.scalar(
                select(BrowserBridgeClient).where(
                    BrowserBridgeClient.token_hash == _token_hash(token),
                    BrowserBridgeClient.status == "paired",
                    BrowserBridgeClient.revoked_at.is_(None),
                )
            )
            if client is None:
                raise ValueError("扩展令牌无效或已撤销")
        elif pairing_code:
            grant = self._pairings.pop(pairing_code, None)
            if grant is None or grant.expires_at <= utc_now():
                raise ValueError("配对码无效或已过期")
            issued_token = secrets.token_urlsafe(32)
            client = BrowserBridgeClient(
                token_hash=_token_hash(issued_token),
                status="paired",
                extension_version=extension_version,
                zhihu_auth="unknown",
                last_seen_at=utc_now(),
            )
            session.add(client)
            await session.flush()
        else:
            raise ValueError("缺少配对码或扩展令牌")
        client.extension_version = extension_version
        client.last_seen_at = utc_now()
        client.last_error = None
        await session.commit()
        return client, issued_token

    async def register(self, client_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            previous = self._connections.pop(client_id, None)
            self._connections[client_id] = ActiveConnection(client_id, websocket)
        if previous:
            await previous.websocket.close(code=4001, reason="扩展已在新连接中上线")

    async def unregister(self, client_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            current = self._connections.get(client_id)
            if current and current.websocket is websocket:
                self._connections.pop(client_id, None)

    async def disconnect_all(self) -> None:
        async with self._lock:
            connections = list(self._connections.values())
            self._connections.clear()
        for item in connections:
            await item.websocket.close(code=4002, reason="配对已撤销")

    async def dispatch_job(
        self, job: CollectionJob, *, client_id: str | None = None
    ) -> str | None:
        connection = (
            self._connections.get(client_id)
            if client_id
            else next(iter(self._connections.values()), None)
        )
        if connection is None:
            return None
        payload = {
            "type": "collect_question",
            "protocol_version": PROTOCOL_VERSION,
            "job_id": job.id,
            "nonce": job.nonce,
            **job.request_json,
        }
        try:
            await connection.websocket.send_json(payload)
        except Exception:
            return None
        return connection.client_id


bridge_manager = BrowserBridgeManager()


async def run_bridge_dispatch_loop(
    *,
    stop_event: asyncio.Event,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """API 进程轮询持久队列，使独立 Worker 创建的任务也能下发给扩展。"""

    while not stop_event.is_set():
        if bridge_manager.connected_client_ids:
            async with session_factory() as session:
                job = await session.scalar(
                    select(CollectionJob)
                    .where(CollectionJob.status == "pending")
                    .order_by(CollectionJob.created_at)
                    .limit(1)
                )
                dispatched_client_id = (
                    await bridge_manager.dispatch_job(job) if job else None
                )
                if job and dispatched_client_id:
                    job.status = "dispatched"
                    job.client_id = dispatched_client_id
                    job.dispatched_at = utc_now()
                    await session.commit()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2)
        except TimeoutError:
            pass


async def create_collection_job(
    session: AsyncSession,
    task: TaskJob,
    *,
    mode: str,
    max_answers: int,
) -> CollectionJob:
    await session.execute(
        update(CollectionJob)
        .where(
            CollectionJob.task_id == task.id,
            CollectionJob.status.in_(["pending", "dispatched"]),
        )
        .values(status="superseded", error_message="已由新的采集请求替代")
    )
    job = CollectionJob(
        task_id=task.id,
        question_id=task.question_id,
        nonce=secrets.token_hex(16),
        status="pending",
        mode=mode,
        max_answers=max_answers,
        source="extension",
        request_json={
            "question_external_id": task.question.external_id,
            "question_url": task.question.url,
            "mode": mode,
            "max_answers": max_answers,
        },
    )
    session.add(job)
    await session.flush()
    task.payload = {**(task.payload or {}), "collection_job_id": job.id}
    task.status = "waiting_browser"
    task.stage = "waiting_browser"
    task.progress = 10
    task.worker_id = None
    task.completed_at = None
    task.error_message = None
    task.question.status = "waiting_browser"
    session.add(
        TaskLog(
            task_id=task.id,
            level="info",
            stage="waiting_browser",
            message="已将采集任务交给 Chrome 扩展，Worker 已释放",
            metadata_json={"collection_job_id": job.id},
        )
    )
    await session.commit()
    return job


async def mark_job_dispatched(session: AsyncSession, job: CollectionJob, client_id: str) -> None:
    job.status = "dispatched"
    job.client_id = client_id
    job.dispatched_at = utc_now()
    await session.commit()


async def complete_collection_job(
    session_factory: async_sessionmaker[AsyncSession],
    broker: QueueBroker,
    *,
    client_id: str,
    job_id: str,
    nonce: str,
    bundle_payload: dict[str, Any],
) -> str:
    try:
        bundle = ImportBundleV1.model_validate(bundle_payload)
    except ValidationError as exc:
        raise ValueError(f"扩展结果格式无效：{exc.errors(include_url=False)}") from exc
    async with session_factory() as session:
        job = await session.get(CollectionJob, job_id)
        if not job or not secrets.compare_digest(job.nonce, nonce):
            raise ValueError("采集任务或 nonce 无效")
        if job.status == "completed":
            return "duplicate"
        if job.status not in {"pending", "dispatched"}:
            raise ValueError("采集任务已经结束或被替代")
        if job.client_id and job.client_id != client_id:
            raise ValueError("当前扩展不是该采集任务的接收方")
        question = await session.get(Question, job.question_id)
        if not question or bundle.question.id != question.external_id:
            raise ValueError("扩展结果的问题 id 与任务不一致")
        if len(bundle.answers) > job.max_answers:
            raise ValueError("扩展返回的回答数量超过任务上限")
        job.status = "completed"
        job.client_id = client_id
        job.result_json = bundle.model_dump(mode="json")
        job.completed_at = utc_now()
        job.error_message = None
        task = await session.get(TaskJob, job.task_id) if job.task_id else None
        should_enqueue = False
        if task and task.status in {
            "waiting_browser",
            "waiting_login",
            "waiting_verification",
        }:
            task.status = "queued"
            should_enqueue = True
            task.stage = "queued"
            task.worker_id = None
            task.error_message = None
            question.status = "queued"
            session.add(
                TaskLog(
                    task_id=task.id,
                    level="info",
                    stage="queued",
                    message=f"Chrome 扩展已回传 {len(bundle.answers)} 条回答，任务重新入队",
                    metadata_json={"collection_job_id": job.id},
                )
            )
        await session.commit()
        if task and should_enqueue:
            try:
                await broker.enqueue(task.id)
            except Exception as exc:
                async with session_factory() as recovery_session:
                    recovery_task = await recovery_session.get(TaskJob, task.id)
                    recovery_job = await recovery_session.get(CollectionJob, job.id)
                    recovery_question = await recovery_session.get(
                        Question, task.question_id
                    )
                    if recovery_task:
                        recovery_task.status = "waiting_browser"
                        recovery_task.stage = "waiting_browser"
                        recovery_task.error_message = (
                            "采集结果已安全保存，但任务队列暂时不可用；请点击重新获取继续恢复。"
                        )
                        if recovery_question:
                            recovery_question.status = "waiting_browser"
                        recovery_session.add(
                            TaskLog(
                                task_id=recovery_task.id,
                                level="error",
                                stage="waiting_browser",
                                message=recovery_task.error_message,
                                metadata_json={"collection_job_id": job.id},
                            )
                        )
                    if recovery_job:
                        recovery_job.error_message = f"重新入队失败：{exc}"[:2000]
                    await recovery_session.commit()
                raise ValueError("采集结果已保存，但任务重新入队失败") from exc
        return "completed"


async def block_collection_job(
    session_factory: async_sessionmaker[AsyncSession],
    broker: QueueBroker,
    *,
    client_id: str,
    job_id: str,
    nonce: str,
    reason: str,
    message: str,
) -> None:
    target = "waiting_login" if reason == "login_required" else "waiting_verification"
    async with session_factory() as session:
        job = await session.get(CollectionJob, job_id)
        if not job or not secrets.compare_digest(job.nonce, nonce):
            raise ValueError("采集任务或 nonce 无效")
        if job.status not in {"pending", "dispatched"}:
            raise ValueError("采集任务已经结束或被替代")
        if job.client_id and job.client_id != client_id:
            raise ValueError("当前扩展不是该采集任务的接收方")
        job.status = "blocked"
        job.client_id = client_id
        job.error_message = message[:2000]
        task = await session.get(TaskJob, job.task_id) if job.task_id else None
        if task:
            question = await session.get(Question, task.question_id)
            task.status = target
            task.stage = target
            task.worker_id = None
            task.completed_at = None
            task.error_message = message[:2000]
            if question:
                question.status = target
            session.add(
                TaskLog(
                    task_id=task.id,
                    level="warning",
                    stage=target,
                    message=message[:2000],
                    metadata_json={"collection_job_id": job.id, "reason": reason},
                )
            )
        await session.commit()
        if task:
            await broker.publish(
                {
                    "type": "task_progress",
                    "task_id": task.id,
                    "question_id": task.question_id,
                    "status": target,
                    "stage": target,
                    "progress": task.progress,
                    "error_message": task.error_message,
                }
            )


async def fail_collection_job(
    session_factory: async_sessionmaker[AsyncSession],
    broker: QueueBroker,
    *,
    client_id: str,
    job_id: str,
    nonce: str,
    message: str,
) -> None:
    async with session_factory() as session:
        job = await session.get(CollectionJob, job_id)
        if not job or not secrets.compare_digest(job.nonce, nonce):
            raise ValueError("采集任务或 nonce 无效")
        if job.status not in {"pending", "dispatched"}:
            raise ValueError("采集任务已经结束或被替代")
        if job.client_id and job.client_id != client_id:
            raise ValueError("当前扩展不是该采集任务的接收方")
        job.status = "failed"
        job.client_id = client_id
        job.error_message = message[:2000]
        task = await session.get(TaskJob, job.task_id) if job.task_id else None
        if task:
            question = await session.get(Question, task.question_id)
            task.status = "waiting_browser"
            task.stage = "waiting_browser"
            task.worker_id = None
            task.error_message = message[:2000]
            if question:
                question.status = "waiting_browser"
            session.add(
                TaskLog(
                    task_id=task.id,
                    level="error",
                    stage="waiting_browser",
                    message=f"扩展采集失败，可重新获取或导入 JSON：{message[:1500]}",
                    metadata_json={"collection_job_id": job.id},
                )
            )
        await session.commit()
        if task:
            await broker.publish(
                {
                    "type": "task_progress",
                    "task_id": task.id,
                    "question_id": task.question_id,
                    "status": task.status,
                    "stage": task.stage,
                    "progress": task.progress,
                    "error_message": task.error_message,
                }
            )
