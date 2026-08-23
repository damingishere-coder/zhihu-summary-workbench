from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.browser import ManagedBrowserSessionRead


router = APIRouter(prefix="/settings/browser/session", tags=["browser"])


@router.get("", response_model=ManagedBrowserSessionRead)
async def get_browser_session(
) -> ManagedBrowserSessionRead:
    _gone()


@router.post("/start", response_model=ManagedBrowserSessionRead)
async def start_browser_session(
) -> ManagedBrowserSessionRead:
    _gone()


@router.post("/refresh", response_model=ManagedBrowserSessionRead)
async def refresh_browser_session(
) -> ManagedBrowserSessionRead:
    _gone()


@router.post("/recheck", response_model=ManagedBrowserSessionRead)
async def recheck_browser_session(
) -> ManagedBrowserSessionRead:
    _gone()


@router.get("/qr")
async def get_browser_login_qr() -> None:
    _gone()


def _gone() -> None:
    raise HTTPException(
        status_code=410,
        detail=(
            "独立 Playwright 扫码登录已退出主流程。请升级前端并在浏览器设置中配对 Chrome 扩展。"
        ),
    )
