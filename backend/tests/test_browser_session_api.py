from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.schemas.browser import ManagedBrowserSessionRead
from backend.app.services import browser_session
from backend.app.services.browser_session import (
    BrowserProfileLease,
    ManagedZhihuBrowserSession,
    ZHIHU_CURRENT_USER_URL,
    browser_session_error_message,
    managed_login_is_headless,
    remove_stale_chromium_profile_locks,
)


class FakeBrowserSession:
    def __init__(self, qr_path) -> None:
        self.qr_path = qr_path
        self.state = ManagedBrowserSessionRead(
            state="idle",
            message="尚未登录知乎",
            updated_at=datetime.now(timezone.utc),
        )

    async def status(self) -> ManagedBrowserSessionRead:
        return self.state

    async def start(self) -> ManagedBrowserSessionRead:
        self.state = ManagedBrowserSessionRead(
            state="qr_ready",
            message="请扫码",
            qr_code_url="/api/settings/browser/session/qr?v=1",
            updated_at=datetime.now(timezone.utc),
        )
        return self.state

    async def refresh(self) -> ManagedBrowserSessionRead:
        self.state = ManagedBrowserSessionRead(
            state="starting",
            message="正在重新生成二维码",
            updated_at=datetime.now(timezone.utc),
        )
        return self.state

    async def recheck(self) -> ManagedBrowserSessionRead:
        self.state = ManagedBrowserSessionRead(
            state="starting",
            message="正在重新检查登录状态",
            updated_at=datetime.now(timezone.utc),
        )
        return self.state


@pytest.mark.asyncio
async def test_browser_session_status_start_and_qr(app_client, tmp_path) -> None:
    _, client, _ = app_client
    requests = [
        ("GET", "/api/settings/browser/session"),
        ("POST", "/api/settings/browser/session/start"),
        ("POST", "/api/settings/browser/session/refresh"),
        ("POST", "/api/settings/browser/session/recheck"),
        ("GET", "/api/settings/browser/session/qr"),
    ]
    for method, path in requests:
        response = await client.request(method, path)
        assert response.status_code == 410
        assert "Chrome 扩展" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/questions/hot/fetch", {"limit": 20, "collector_mode": "auto"}),
        (
            "/api/questions/does-not-matter/fetch-answers",
            {"mode": "representative", "max_answers": 20, "collector_mode": "auto"},
        ),
    ],
)
async def test_legacy_playwright_collection_routes_return_gone(
    app_client, path, payload
) -> None:
    _, client, _ = app_client
    response = await client.post(path, json=payload)
    assert response.status_code == 410
    assert "Playwright" in response.json()["detail"]


def test_normal_sms_login_copy_is_not_treated_as_risk_verification() -> None:
    assert (
        ManagedZhihuBrowserSession._verification_required(
            "验证码登录 密码登录 获取短信验证码"
        )
        is False
    )
    assert (
        ManagedZhihuBrowserSession._verification_required(
            "您的请求存在异常，请完成安全验证"
        )
        is True
    )
    assert (
        ManagedZhihuBrowserSession._scan_confirmation_pending(
            "二维码扫描成功，请在手机上确认登录"
        )
        is True
    )
    assert (
        ManagedZhihuBrowserSession._scan_confirmation_pending(
            "请使用知乎 App 扫描二维码登录"
        )
        is False
    )


def test_browser_profile_lock_releases_without_deleting_lock_file(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "browser"
    monkeypatch.setattr(browser_session, "MANAGED_BROWSER_ROOT", root)
    monkeypatch.setattr(
        browser_session,
        "PROFILE_LOCK_PATH",
        root / ".profile.lock",
    )
    first = BrowserProfileLease()
    second = BrowserProfileLease()

    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()
    assert browser_session.PROFILE_LOCK_PATH.exists()


def test_managed_login_uses_a_normal_browser_by_default(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MANAGED_LOGIN_HEADLESS", raising=False)
    assert managed_login_is_headless() is False
    monkeypatch.setenv("MANAGED_LOGIN_HEADLESS", "true")
    assert managed_login_is_headless() is True


def test_missing_x_server_error_is_sanitized() -> None:
    raw_error = RuntimeError(
        "BrowserType.launch_persistent_context: Target page, context or "
        "browser has been closed\n"
        "Looks like you launched a headed browser without having a XServer "
        "running.\n"
        "Missing X server or $DISPLAY"
    )

    message = browser_session_error_message(raw_error)

    assert message == "工作台浏览器显示服务异常，请重启工作台后再试。"
    assert "BrowserType" not in message
    assert "XServer" not in message


def test_missing_playwright_browser_component_is_sanitized() -> None:
    raw_error = RuntimeError(
        "BrowserType.launch: Executable doesn't exist at /root/.cache/browser\n"
        "Please run: playwright install"
    )

    message = browser_session_error_message(raw_error)

    assert message == (
        "工作台浏览器组件未安装完整，请重新构建并启动工作台后再试。"
    )
    assert "/root/.cache/browser" not in message


def test_expected_browser_session_error_remains_actionable() -> None:
    message = browser_session_error_message(
        RuntimeError("知乎登录页未显示二维码，页面结构可能已经变化")
    )

    assert message == "知乎登录页未显示二维码，页面结构可能已经变化"


def test_unexpected_browser_error_does_not_leak_details() -> None:
    message = browser_session_error_message(
        RuntimeError("Target page, context or browser has been closed\nsecret")
    )

    assert message == (
        "工作台浏览器暂时无法完成登录操作，请稍后重试；"
        "详细原因已记录在后端日志中。"
    )
    assert "secret" not in message


def test_profile_in_use_error_is_sanitized() -> None:
    message = browser_session_error_message(
        RuntimeError(
            "The profile appears to be in use by another Chromium process "
            "(192191) on another computer"
        )
    )

    assert message == (
        "工作台浏览器资料仍被其他进程占用，请稍后重试或重启工作台。"
    )
    assert "192191" not in message


def test_only_stale_chromium_singleton_files_are_removed(tmp_path) -> None:
    profile = tmp_path / "zhihu-profile"
    profile.mkdir()
    for filename in (
        "SingletonCookie",
        "SingletonLock",
        "SingletonSocket",
    ):
        (profile / filename).write_text("stale", encoding="utf-8")
    login_data = profile / "Login Data"
    cookies = profile / "Cookies"
    login_data.write_text("preserve", encoding="utf-8")
    cookies.write_text("preserve", encoding="utf-8")

    remove_stale_chromium_profile_locks(profile)

    assert not (profile / "SingletonCookie").exists()
    assert not (profile / "SingletonLock").exists()
    assert not (profile / "SingletonSocket").exists()
    assert login_data.read_text(encoding="utf-8") == "preserve"
    assert cookies.read_text(encoding="utf-8") == "preserve"


@pytest.mark.asyncio
async def test_closing_an_already_closed_browser_context_is_safe() -> None:
    class AlreadyClosedContext:
        async def close(self) -> None:
            raise RuntimeError("Target page, context or browser has been closed")

    await ManagedZhihuBrowserSession._close_context_safely(
        AlreadyClosedContext()
    )


@pytest.mark.asyncio
async def test_new_session_cookie_is_only_a_browser_signal() -> None:
    class Locator:
        def __init__(self, *, visible: bool = False, text: str = "") -> None:
            self.visible = visible
            self.text = text

        async def is_visible(self) -> bool:
            return self.visible

        async def inner_text(self) -> str:
            return self.text

    class Page:
        url = "https://www.zhihu.com/signin"

        def locator(self, selector: str) -> Locator:
            if selector == "body":
                return Locator(text="请使用知乎 App 扫描二维码登录")
            return Locator(visible=True)

    class Context:
        async def cookies(self, _url: str) -> list[dict[str, str]]:
            return [{"name": "z_c0", "value": "new-session"}]

    assert (
        await ManagedZhihuBrowserSession._login_succeeded(
            Page(),
            Context(),
            session_cookie_before_scan=None,
            accept_cookie_change=True,
        )
        is True
    )
    assert (
        ManagedZhihuBrowserSession._should_mark_authenticated(
            browser_reports_login=True,
            api_reports_login=False,
        )
        is False
    )
    assert (
        ManagedZhihuBrowserSession._should_mark_authenticated(
            browser_reports_login=False,
            api_reports_login=True,
        )
        is True
    )


@pytest.mark.asyncio
async def test_unchanged_stale_cookie_does_not_fake_login() -> None:
    class Locator:
        async def is_visible(self) -> bool:
            return True

        async def inner_text(self) -> str:
            return "请使用知乎 App 扫描二维码登录"

    class Page:
        url = "https://www.zhihu.com/signin"

        def locator(self, _selector: str) -> Locator:
            return Locator()

    class Context:
        async def cookies(self, _url: str) -> list[dict[str, str]]:
            return [{"name": "z_c0", "value": "stale-session"}]

    assert (
        await ManagedZhihuBrowserSession._login_succeeded(
            Page(),
            Context(),
            session_cookie_before_scan="stale-session",
            accept_cookie_change=True,
        )
        is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "payload", "expected"),
    [
        (200, {"id": "user-id", "name": "测试用户"}, True),
        (200, {"is_login": True}, True),
        (200, {"is_login": False}, False),
        (200, {}, False),
        (401, {"id": "user-id", "name": "测试用户"}, False),
        (403, {"id": "user-id", "name": "测试用户"}, False),
    ],
)
async def test_official_current_user_endpoint_verifies_login(
    status_code: int,
    payload: dict[str, object],
    expected: bool,
) -> None:
    class Response:
        status = status_code
        disposed = False

        async def json(self) -> dict[str, object]:
            return payload

        async def dispose(self) -> None:
            self.disposed = True

    class Request:
        def __init__(self) -> None:
            self.response = Response()

        async def get(self, url: str, *, timeout: int) -> Response:
            assert url == ZHIHU_CURRENT_USER_URL
            assert timeout == 10_000
            return self.response

    class Context:
        request = Request()

    context = Context()
    assert (
        await ManagedZhihuBrowserSession._authenticated_via_official_api(
            context
        )
        is expected
    )
    assert context.request.response.disposed is True


@pytest.mark.asyncio
async def test_official_login_check_rejects_non_json_success() -> None:
    class Response:
        status = 200

        async def json(self):
            raise ValueError("HTML response")

        async def dispose(self) -> None:
            return None

    class Request:
        async def get(self, _url: str, *, timeout: int) -> Response:
            assert timeout == 10_000
            return Response()

    class Context:
        request = Request()

    assert (
        await ManagedZhihuBrowserSession._authenticated_via_official_api(
            Context()
        )
        is False
    )


@pytest.mark.asyncio
async def test_official_login_check_network_error_is_not_login() -> None:
    class Request:
        async def get(self, _url: str, *, timeout: int):
            assert timeout == 10_000
            raise RuntimeError("temporary network failure")

    class Context:
        request = Request()

    assert (
        await ManagedZhihuBrowserSession._authenticated_via_official_api(
            Context()
        )
        is False
    )


@pytest.mark.asyncio
async def test_forbidden_official_check_is_unknown_not_logged_out() -> None:
    class Response:
        status = 403

        async def dispose(self) -> None:
            return None

    class Request:
        async def get(self, _url: str, *, timeout: int) -> Response:
            assert timeout == 10_000
            return Response()

    class Context:
        request = Request()

    assert (
        await ManagedZhihuBrowserSession._official_authentication_state(
            Context()
        )
        == "unknown"
    )


@pytest.mark.asyncio
async def test_cached_authenticated_state_expires_when_marker_is_removed(
    monkeypatch,
    tmp_path,
) -> None:
    marker_path = tmp_path / "authenticated.json"
    monkeypatch.setattr(
        browser_session,
        "AUTHENTICATED_MARKER_PATH",
        marker_path,
    )
    manager = ManagedZhihuBrowserSession()
    manager._state = ManagedBrowserSessionRead(
        state="authenticated",
        authenticated=True,
        message="知乎扫码登录成功",
        updated_at=datetime.now(timezone.utc),
    )

    async def skip_persist() -> None:
        return None

    monkeypatch.setattr(manager, "_persist_state", skip_persist)

    state = await manager.status()

    assert state.state == "expired"
    assert "失效" in state.message


@pytest.mark.asyncio
async def test_verification_state_preserves_authenticated_marker(
    monkeypatch,
    tmp_path,
) -> None:
    marker_path = tmp_path / "authenticated.json"
    marker_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        browser_session,
        "AUTHENTICATED_MARKER_PATH",
        marker_path,
    )
    manager = ManagedZhihuBrowserSession()

    async def skip_persist() -> None:
        return None

    monkeypatch.setattr(manager, "_persist_state", skip_persist)
    await manager._set_state(
        "verification_required",
        "知乎暂时拦截本次请求",
    )

    state = await manager.status()
    assert state.state == "verification_required"
    assert state.authenticated is True
    assert marker_path.exists()
