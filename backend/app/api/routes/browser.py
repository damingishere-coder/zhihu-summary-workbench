from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.app.schemas.browser import ManagedBrowserSessionRead


router = APIRouter(prefix="/settings/browser/session", tags=["browser"])


@router.get("", response_model=ManagedBrowserSessionRead)
async def get_browser_session(
    request: Request,
) -> ManagedBrowserSessionRead:
    return await request.app.state.zhihu_browser_session.status()


@router.post("/start", response_model=ManagedBrowserSessionRead)
async def start_browser_session(
    request: Request,
) -> ManagedBrowserSessionRead:
    return await request.app.state.zhihu_browser_session.start()


@router.post("/refresh", response_model=ManagedBrowserSessionRead)
async def refresh_browser_session(
    request: Request,
) -> ManagedBrowserSessionRead:
    return await request.app.state.zhihu_browser_session.refresh()


@router.post("/recheck", response_model=ManagedBrowserSessionRead)
async def recheck_browser_session(
    request: Request,
) -> ManagedBrowserSessionRead:
    return await request.app.state.zhihu_browser_session.recheck()


@router.get("/qr")
async def get_browser_login_qr(request: Request) -> FileResponse:
    manager = request.app.state.zhihu_browser_session
    state = await manager.status()
    if state.state != "qr_ready" or not manager.qr_path.is_file():
        raise HTTPException(status_code=404, detail="当前没有可用的登录二维码")
    return FileResponse(
        manager.qr_path,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )
