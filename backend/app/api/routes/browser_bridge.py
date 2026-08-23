from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session, get_session_factory
from backend.app.models.browser_bridge import BrowserBridgeClient, CollectionJob
from backend.app.models.common import utc_now
from backend.app.schemas.browser_bridge import (
    BrowserBridgeStatus,
    MAX_BRIDGE_PAYLOAD_BYTES,
    PairingStartResponse,
    PROTOCOL_VERSION,
    UnpairResponse,
)
from backend.app.services.browser_bridge import (
    block_collection_job,
    bridge_manager,
    complete_collection_job,
    fail_collection_job,
    mark_job_dispatched,
)


router = APIRouter(prefix="/settings/browser/bridge", tags=["browser-bridge"])


@router.get("", response_model=BrowserBridgeStatus)
async def get_bridge_status(
    session: AsyncSession = Depends(get_db_session),
) -> BrowserBridgeStatus:
    client = await session.scalar(
        select(BrowserBridgeClient)
        .where(
            BrowserBridgeClient.status == "paired",
            BrowserBridgeClient.revoked_at.is_(None),
        )
        .order_by(BrowserBridgeClient.last_seen_at.desc())
        .limit(1)
    )
    if client is None:
        return BrowserBridgeStatus(
            connection="unpaired",
            zhihu_auth="unknown",
            message="尚未配对 Chrome 扩展",
        )
    connected = client.id in bridge_manager.connected_client_ids
    active_job = await session.scalar(
        select(CollectionJob)
        .where(CollectionJob.status.in_(["pending", "dispatched"]))
        .order_by(CollectionJob.created_at)
        .limit(1)
    )
    if not connected:
        message = "扩展已配对但当前未连接"
    elif client.zhihu_auth == "authenticated":
        message = "扩展在线，知乎实时登录状态正常"
    elif client.zhihu_auth == "login_required":
        message = "扩展在线，请在正常知乎标签页登录"
    elif client.zhihu_auth == "verification_required":
        message = "扩展在线，知乎要求人工完成安全验证"
    else:
        message = "扩展在线，等待知乎实时登录检查"
    return BrowserBridgeStatus(
        connection="connected" if connected else "disconnected",
        zhihu_auth=client.zhihu_auth,
        extension_version=client.extension_version,
        last_seen_at=client.last_seen_at,
        last_check_at=client.last_check_at,
        active_job_id=active_job.id if active_job else None,
        message=message,
    )


@router.post("/pairing", response_model=PairingStartResponse)
async def start_pairing(request: Request) -> PairingStartResponse:
    grant = bridge_manager.create_pairing()
    scheme = "wss" if request.url.scheme == "https" else "ws"
    return PairingStartResponse(
        pairing_code=grant.code,
        expires_at=grant.expires_at,
        websocket_url=f"{scheme}://{request.url.netloc}/api/settings/browser/bridge/socket",
        message="请在 10 分钟内把配对码输入 Chrome 扩展；配对码只能使用一次",
    )


@router.post("/unpair", response_model=UnpairResponse)
async def unpair_bridge(
    session: AsyncSession = Depends(get_db_session),
) -> UnpairResponse:
    result = await session.execute(
        update(BrowserBridgeClient)
        .where(
            BrowserBridgeClient.status == "paired",
            BrowserBridgeClient.revoked_at.is_(None),
        )
        .values(status="revoked", revoked_at=utc_now())
    )
    await session.commit()
    await bridge_manager.disconnect_all()
    return UnpairResponse(
        revoked_clients=int(result.rowcount or 0),
        message="扩展配对已撤销；旧令牌不能再次连接",
    )


@router.websocket("/socket")
async def bridge_socket(websocket: WebSocket) -> None:
    if not bridge_origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=1008, reason="不允许的 WebSocket Origin")
        return
    await websocket.accept()
    client: BrowserBridgeClient | None = None
    try:
        hello = await _receive_payload(websocket)
        if hello.get("type") != "hello":
            raise ValueError("第一条消息必须是 hello")
        async with get_session_factory()() as session:
            client, issued_token = await bridge_manager.authenticate_hello(session, hello)
        await bridge_manager.register(client.id, websocket)
        await websocket.send_json(
            {
                "type": "paired" if issued_token else "hello_ack",
                "protocol_version": PROTOCOL_VERSION,
                "job_id": None,
                "nonce": str(hello.get("nonce") or ""),
                "client_id": client.id,
                "token": issued_token,
                "message": "Chrome 扩展桥接已连接",
            }
        )
        await _dispatch_oldest_job(client.id)
        while True:
            payload = await _receive_payload(websocket)
            await _handle_message(client.id, payload, websocket)
    except WebSocketDisconnect:
        pass
    except ValueError as exc:
        await websocket.send_json(
            {
                "type": "protocol_error",
                "protocol_version": PROTOCOL_VERSION,
                "job_id": None,
                "nonce": "",
                "message": str(exc),
            }
        )
        await websocket.close(code=1008, reason="协议校验失败")
    finally:
        if client:
            await bridge_manager.unregister(client.id, websocket)


async def _receive_payload(websocket: WebSocket) -> dict[str, Any]:
    text = await websocket.receive_text()
    if len(text.encode("utf-8")) > MAX_BRIDGE_PAYLOAD_BYTES:
        raise ValueError("扩展消息超过 6 MiB 上限")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("扩展消息不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("扩展消息必须是 JSON 对象")
    if int(payload.get("protocol_version") or 0) != PROTOCOL_VERSION:
        raise ValueError("扩展协议版本不兼容")
    nonce = str(payload.get("nonce") or "")
    if not nonce or len(nonce) > 128:
        raise ValueError("扩展消息缺少有效 nonce")
    return payload


async def _dispatch_oldest_job(client_id: str) -> bool:
    async with get_session_factory()() as session:
        job = await session.scalar(
            select(CollectionJob)
            .where(CollectionJob.status.in_(["pending", "dispatched"]))
            .order_by(CollectionJob.created_at)
            .limit(1)
        )
        if job is None:
            return False
        dispatched_client_id = await bridge_manager.dispatch_job(job, client_id=client_id)
        if dispatched_client_id:
            await mark_job_dispatched(session, job, dispatched_client_id)
        return bool(dispatched_client_id)


async def _touch_client(client_id: str, *, auth: str | None = None, error: str | None = None) -> None:
    async with get_session_factory()() as session:
        client = await session.get(BrowserBridgeClient, client_id)
        if not client:
            return
        client.last_seen_at = utc_now()
        if auth is not None:
            if auth not in {
                "authenticated",
                "login_required",
                "verification_required",
                "unknown",
            }:
                raise ValueError("未知的知乎登录状态")
            client.zhihu_auth = auth
            client.last_check_at = utc_now()
        client.last_error = error[:2000] if error else None
        await session.commit()


async def _handle_message(
    client_id: str, payload: dict[str, Any], websocket: WebSocket
) -> None:
    message_type = str(payload.get("type") or "")
    await _touch_client(client_id)
    if message_type == "auth_state":
        await _touch_client(client_id, auth=str(payload.get("zhihu_auth") or "unknown"))
    elif message_type == "progress":
        await websocket.send_json(
            {
                "type": "progress_ack",
                "protocol_version": PROTOCOL_VERSION,
                "job_id": payload.get("job_id"),
                "nonce": payload.get("nonce"),
            }
        )
    elif message_type == "completed":
        result = await complete_collection_job(
            get_session_factory(),
            websocket.app.state.broker,
            client_id=client_id,
            job_id=_required_job_id(payload),
            nonce=str(payload["nonce"]),
            bundle_payload=payload.get("bundle") or {},
        )
        await websocket.send_json(
            {
                "type": "completed_ack",
                "protocol_version": PROTOCOL_VERSION,
                "job_id": payload.get("job_id"),
                "nonce": payload.get("nonce"),
                "result": result,
            }
        )
        await _dispatch_oldest_job(client_id)
    elif message_type == "blocked":
        reason = str(payload.get("reason") or "verification_required")
        if reason not in {"login_required", "verification_required"}:
            raise ValueError("blocked.reason 无效")
        await block_collection_job(
            get_session_factory(),
            websocket.app.state.broker,
            client_id=client_id,
            job_id=_required_job_id(payload),
            nonce=str(payload["nonce"]),
            reason=reason,
            message=str(payload.get("message") or "知乎要求用户处理")[:2000],
        )
        await _touch_client(client_id, auth=reason)
    elif message_type == "failed":
        await fail_collection_job(
            get_session_factory(),
            websocket.app.state.broker,
            client_id=client_id,
            job_id=_required_job_id(payload),
            nonce=str(payload["nonce"]),
            message=str(payload.get("message") or "扩展采集失败")[:2000],
        )
        await _touch_client(client_id, error=str(payload.get("message") or "扩展采集失败"))
    else:
        raise ValueError(f"不支持的扩展消息类型：{message_type}")


def _required_job_id(payload: dict[str, Any]) -> str:
    job_id = str(payload.get("job_id") or "")
    if not job_id or len(job_id) > 64:
        raise ValueError("扩展消息缺少有效 job_id")
    return job_id


def bridge_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    parsed = urlsplit(origin)
    if parsed.scheme == "chrome-extension" and re.fullmatch(r"[a-p]{32}", parsed.netloc):
        return True
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "127.0.0.1",
        "localhost",
    }
