from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Literal

from sqlalchemy import select

from backend.app.core.config import REPOSITORY_ROOT
from backend.app.db.session import get_session_factory
from backend.app.models.media import BrowserSession
from backend.app.schemas.browser import ManagedBrowserSessionRead


logger = logging.getLogger(__name__)

MANAGED_BROWSER_ROOT = (REPOSITORY_ROOT / "data" / "browser").resolve()
MANAGED_PROFILE_DIR = (MANAGED_BROWSER_ROOT / "zhihu-profile").resolve()
LOGIN_QR_PATH = (MANAGED_BROWSER_ROOT / "zhihu-login.png").resolve()
AUTHENTICATED_MARKER_PATH = (
    MANAGED_BROWSER_ROOT / "zhihu-authenticated.json"
).resolve()
PROFILE_LOCK_PATH = (MANAGED_BROWSER_ROOT / ".zhihu-profile.lock").resolve()
CHROMIUM_SINGLETON_FILES = (
    "SingletonCookie",
    "SingletonLock",
    "SingletonSocket",
)

LOGIN_TIMEOUT_SECONDS = 300
LOGIN_POLL_SECONDS = 2
LOGIN_AUTH_CHECK_SECONDS = 5
ZHIHU_CURRENT_USER_URL = "https://www.zhihu.com/api/v4/me"
OfficialAuthenticationState = Literal[
    "authenticated",
    "unauthenticated",
    "unknown",
]


def managed_browser_profile_path() -> Path:
    return MANAGED_PROFILE_DIR


def managed_browser_session_is_authenticated() -> bool:
    return AUTHENTICATED_MARKER_PATH.is_file()


def mark_managed_browser_session_invalid() -> None:
    AUTHENTICATED_MARKER_PATH.unlink(missing_ok=True)


async def close_browser_context_safely(context) -> None:
    try:
        await context.close()
    except Exception:
        # Playwright may already have closed a persistent context while its
        # manager is shutting down. Cleanup must never replace the real result.
        logger.debug("知乎浏览器上下文已经关闭", exc_info=True)


def managed_login_is_headless() -> bool:
    return os.getenv("MANAGED_LOGIN_HEADLESS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


SAFE_BROWSER_ERROR_PREFIXES = (
    "未安装 Playwright，",
    "知乎登录页未显示二维码，",
)


def browser_session_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    normalized = message.lower()

    if "profile appears to be in use by another chromium process" in normalized:
        return "工作台浏览器资料仍被其他进程占用，请稍后重试或重启工作台。"

    if (
        "headed browser without having a xserver" in normalized
        or "missing x server or $display" in normalized
        or "the platform failed to initialize" in normalized
    ):
        return "工作台浏览器显示服务异常，请重启工作台后再试。"

    if (
        "executable doesn't exist" in normalized
        or "playwright install" in normalized
    ):
        return "工作台浏览器组件未安装完整，请重新构建并启动工作台后再试。"

    if any(message.startswith(prefix) for prefix in SAFE_BROWSER_ERROR_PREFIXES):
        return message

    return (
        "工作台浏览器暂时无法完成登录操作，请稍后重试；"
        "详细原因已记录在后端日志中。"
    )


def remove_stale_chromium_profile_locks(profile_path: Path) -> None:
    # BrowserProfileLease must be held before calling this function. Chromium
    # can leave these process-singleton entries behind after a container crash;
    # they do not contain login data and block the next browser from starting.
    for filename in CHROMIUM_SINGLETON_FILES:
        (profile_path / filename).unlink(missing_ok=True)


class BrowserProfileLease:
    def __init__(self) -> None:
        self.acquired = False
        self._file: BinaryIO | None = None

    def acquire(self) -> bool:
        MANAGED_BROWSER_ROOT.mkdir(parents=True, exist_ok=True)
        lock_file = PROFILE_LOCK_PATH.open("a+b")
        try:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
        except (BlockingIOError, OSError):
            try:
                lock_file.close()
            except OSError:
                pass
            return False
        self._file = lock_file
        self.acquired = True
        return True

    def release(self) -> None:
        if not self.acquired or self._file is None:
            return
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
        self.acquired = False

    def __enter__(self) -> BrowserProfileLease:
        if not self.acquire():
            raise RuntimeError("工作台浏览器正在执行其他操作，请稍后重试")
        return self

    def __exit__(self, *_args) -> None:
        self.release()


class ManagedZhihuBrowserSession:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self._state = ManagedBrowserSessionRead(
            state="idle",
            authenticated=False,
            message="尚未登录知乎",
            updated_at=now,
        )
        self._task: asyncio.Task[None] | None = None
        self._state_lock = asyncio.Lock()

    @property
    def qr_path(self) -> Path:
        return LOGIN_QR_PATH

    async def status(self) -> ManagedBrowserSessionRead:
        marker_exists = managed_browser_session_is_authenticated()
        if self._state.authenticated and not marker_exists:
            await self._set_state(
                "expired",
                "知乎登录会话已失效，请重新扫码登录",
                authenticated=False,
            )
        elif self._state.state == "idle" and marker_exists:
            await self._set_state(
                "authenticated",
                "知乎登录会话可用",
                authenticated=True,
                persist=False,
            )
        return self._state.model_copy()

    async def start(self) -> ManagedBrowserSessionRead:
        return await self._start(restart=False)

    async def refresh(self) -> ManagedBrowserSessionRead:
        return await self._start(restart=True)

    async def recheck(self) -> ManagedBrowserSessionRead:
        async with self._state_lock:
            await self._cancel_active_task()
            LOGIN_QR_PATH.unlink(missing_ok=True)
            await self._set_state(
                "starting",
                "正在使用已有浏览器会话重新检查知乎登录状态",
            )
            self._task = asyncio.create_task(self._run_recheck())
            return self._state.model_copy()

    async def _start(self, *, restart: bool) -> ManagedBrowserSessionRead:
        async with self._state_lock:
            if self._task and not self._task.done() and not restart:
                return self._state.model_copy()
            if restart:
                await self._cancel_active_task()
            LOGIN_QR_PATH.unlink(missing_ok=True)
            await self._set_state(
                "starting",
                (
                    "正在重新生成知乎登录二维码"
                    if restart
                    else "正在打开工作台专属知乎登录页"
                ),
            )
            self._task = asyncio.create_task(self._run_login())
            return self._state.model_copy()

    async def _cancel_active_task(self) -> None:
        if not self._task or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def shutdown(self) -> None:
        await self._cancel_active_task()

    async def _set_state(
        self,
        state: str,
        message: str,
        *,
        qr_ready: bool = False,
        authenticated: bool | None = None,
        persist: bool = True,
    ) -> None:
        updated_at = datetime.now(timezone.utc)
        self._state = ManagedBrowserSessionRead(
            state=state,
            authenticated=(
                managed_browser_session_is_authenticated()
                if authenticated is None
                else authenticated
            ),
            message=message,
            qr_code_url=(
                f"/api/settings/browser/session/qr?v={int(updated_at.timestamp() * 1_000_000)}"
                if qr_ready
                else None
            ),
            updated_at=updated_at,
        )
        if persist:
            await self._persist_state()

    async def _persist_state(self) -> None:
        async with get_session_factory()() as session:
            row = await session.scalar(
                select(BrowserSession)
                .where(BrowserSession.adapter == "zhihu")
                .order_by(BrowserSession.updated_at.desc())
                .limit(1)
            )
            if not row:
                row = BrowserSession(adapter="zhihu")
                session.add(row)
            row.status = self._state.state
            row.profile_reference = (
                str(MANAGED_PROFILE_DIR)
                if self._state.authenticated
                else ""
            )
            row.last_error = (
                self._state.message
                if self._state.state
                in {"expired", "verification_required", "failed"}
                else None
            )
            await session.commit()

    async def _run_recheck(self) -> None:
        lease = BrowserProfileLease()
        if not lease.acquire():
            await self._set_state(
                "failed",
                "工作台浏览器正在执行采集或其他操作，请稍后重试",
            )
            return
        context = None
        try:
            if not MANAGED_PROFILE_DIR.exists():
                mark_managed_browser_session_invalid()
                await self._set_state(
                    "expired",
                    "工作台知乎浏览器会话不存在，请重新扫码登录",
                    authenticated=False,
                )
                return
            remove_stale_chromium_profile_locks(MANAGED_PROFILE_DIR)
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise RuntimeError("未安装 Playwright，无法检查知乎登录状态") from exc

            async with async_playwright() as playwright:
                context = await playwright.chromium.launch_persistent_context(
                    str(MANAGED_PROFILE_DIR),
                    headless=managed_login_is_headless(),
                )
                auth_state = await self._official_authentication_state(context)
                if auth_state == "authenticated":
                    await self._mark_authenticated(
                        message="知乎登录仍然有效，可以继续原采集任务"
                    )
                    return
                if auth_state == "unauthenticated":
                    mark_managed_browser_session_invalid()
                    await self._set_state(
                        "expired",
                        "知乎官方接口确认登录已失效，请重新扫码登录",
                        authenticated=False,
                    )
                    return
                await self._set_state(
                    "verification_required",
                    "知乎暂时拦截了登录检查；已保留原登录会话，请完成验证后再次检查",
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("重新检查知乎登录状态失败")
            await self._set_state(
                "failed",
                browser_session_error_message(exc),
            )
        finally:
            if context is not None:
                await self._close_context_safely(context)
            lease.release()

    async def _run_login(self) -> None:
        lease = BrowserProfileLease()
        if not lease.acquire():
            await self._set_state(
                "failed",
                "工作台浏览器正在执行采集或其他操作，请稍后重试",
            )
            return
        context = None
        try:
            MANAGED_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            remove_stale_chromium_profile_locks(MANAGED_PROFILE_DIR)
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise RuntimeError("未安装 Playwright，无法启动知乎登录页") from exc

            async with async_playwright() as playwright:
                context = await playwright.chromium.launch_persistent_context(
                    str(MANAGED_PROFILE_DIR),
                    headless=managed_login_is_headless(),
                )
                page = (
                    context.pages[0]
                    if context.pages
                    else await context.new_page()
                )
                await page.goto(
                    "https://www.zhihu.com/signin",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await page.wait_for_timeout(1_500)

                auth_state = await self._official_authentication_state(context)
                if auth_state == "authenticated":
                    await self._mark_authenticated()
                    return
                if auth_state == "unauthenticated":
                    mark_managed_browser_session_invalid()
                session_cookie_before_scan = await self._session_cookie(context)

                page_text = (await page.locator("body").inner_text())[:10_000]
                if self._verification_required(page_text):
                    await self._set_state(
                        "verification_required",
                        "知乎要求人工完成安全验证，请先在知乎 App 中处理后再刷新二维码",
                    )
                    return

                qr = page.locator("canvas.Qrcode-qrcode").first
                try:
                    await qr.wait_for(state="visible", timeout=15_000)
                except Exception as exc:
                    raise RuntimeError(
                        "知乎登录页未显示二维码，页面结构可能已经变化"
                    ) from exc
                await qr.screenshot(path=str(LOGIN_QR_PATH))
                await self._set_state(
                    "qr_ready",
                    "请使用知乎 App 扫描二维码登录",
                    qr_ready=True,
                )

                deadline = asyncio.get_running_loop().time() + LOGIN_TIMEOUT_SECONDS
                next_api_check = 0.0
                while asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(LOGIN_POLL_SECONDS)
                    browser_reports_login = await self._login_succeeded(
                        page,
                        context,
                        session_cookie_before_scan=session_cookie_before_scan,
                        accept_cookie_change=True,
                    )
                    now = asyncio.get_running_loop().time()
                    should_check_api = browser_reports_login or now >= next_api_check
                    api_reports_login = False
                    if should_check_api:
                        api_reports_login = (
                            await self._authenticated_via_official_api(context)
                        )
                        next_api_check = now + LOGIN_AUTH_CHECK_SECONDS
                    if self._should_mark_authenticated(
                        browser_reports_login=browser_reports_login,
                        api_reports_login=api_reports_login,
                    ):
                        await self._mark_authenticated()
                        return
                    page_text = (
                        await page.locator("body").inner_text()
                    )[:10_000]
                    if (
                        self._state.state == "qr_ready"
                        and self._scan_confirmation_pending(page_text)
                    ):
                        await self._set_state(
                            "scanned",
                            "二维码已扫描，请在知乎 App 中点击确认登录",
                        )
                    if self._verification_required(page_text):
                        await self._set_state(
                            "verification_required",
                            "知乎要求人工完成安全验证；原登录会话已保留，请处理后重新检查",
                        )
                        return
                    if "二维码已失效" in page_text or "刷新二维码" in page_text:
                        await self._set_state(
                            "expired",
                            "登录二维码已失效，请点击刷新二维码",
                        )
                        return
                await self._set_state(
                    "expired",
                    "登录二维码已过期，请点击刷新二维码",
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("知乎扫码登录流程失败")
            await self._set_state(
                "failed",
                browser_session_error_message(exc),
            )
        finally:
            if context is not None:
                await self._close_context_safely(context)
            lease.release()

    @staticmethod
    async def _close_context_safely(context) -> None:
        await close_browser_context_safely(context)

    async def _mark_authenticated(
        self,
        *,
        message: str = "知乎扫码登录成功，工作台浏览器会话已保存",
    ) -> None:
        MANAGED_BROWSER_ROOT.mkdir(parents=True, exist_ok=True)
        AUTHENTICATED_MARKER_PATH.write_text(
            json.dumps(
                {"authenticated_at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        LOGIN_QR_PATH.unlink(missing_ok=True)
        await self._set_state(
            "authenticated",
            message,
            authenticated=True,
        )

    @staticmethod
    async def _session_cookie(context) -> str | None:
        cookies = await context.cookies("https://www.zhihu.com")
        return next(
            (
                str(item["value"])
                for item in cookies
                if item.get("name") == "z_c0" and item.get("value")
            ),
            None,
        )

    @staticmethod
    async def _official_authentication_state(
        context,
    ) -> OfficialAuthenticationState:
        response = None
        try:
            response = await context.request.get(
                ZHIHU_CURRENT_USER_URL,
                timeout=10_000,
            )
            if response.status == 401:
                return "unauthenticated"
            if response.status != 200:
                return "unknown"
            try:
                payload = await response.json()
            except Exception:
                return "unknown"
            if not isinstance(payload, dict):
                return "unknown"
            if payload.get("is_login") is True:
                return "authenticated"
            if payload.get("is_login") is False:
                return "unauthenticated"
            if payload.get("id") and payload.get("name"):
                return "authenticated"
            return "unknown"
        except Exception:
            logger.debug("知乎登录状态接口暂时不可用", exc_info=True)
            return "unknown"
        finally:
            if response is not None:
                await response.dispose()

    @classmethod
    async def _authenticated_via_official_api(cls, context) -> bool:
        return (
            await cls._official_authentication_state(context)
            == "authenticated"
        )

    @classmethod
    async def _login_succeeded(
        cls,
        page,
        context,
        *,
        session_cookie_before_scan: str | None = None,
        accept_cookie_change: bool = False,
    ) -> bool:
        session_cookie = await cls._session_cookie(context)
        if not session_cookie:
            return False
        cookie_created_or_changed = (
            accept_cookie_change
            and session_cookie != session_cookie_before_scan
        )
        qr_visible = await page.locator("canvas.Qrcode-qrcode").is_visible()
        return bool(
            cookie_created_or_changed
            or "/signin" not in page.url
            or not qr_visible
        )

    @staticmethod
    def _should_mark_authenticated(
        *,
        browser_reports_login: bool,
        api_reports_login: bool,
    ) -> bool:
        # Browser UI and cookie changes are useful signals to check the official
        # endpoint sooner, but only /api/v4/me returning 200 proves the session.
        del browser_reports_login
        return api_reports_login

    @staticmethod
    def _scan_confirmation_pending(page_text: str) -> bool:
        return any(
            marker in page_text
            for marker in (
                "扫码成功",
                "扫描成功",
                "请在手机上确认",
                "请在手机端确认",
            )
        )

    @staticmethod
    def _verification_required(page_text: str) -> bool:
        normalized = " ".join(page_text.split())
        return any(
            marker in normalized
            for marker in (
                "请完成安全验证",
                "请先完成安全验证",
                "您的请求存在异常",
                "当前请求存在异常",
                "检测到异常行为",
                "访问异常，请稍后重试",
                "暂时限制访问",
            )
        )
