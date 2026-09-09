import pytest
from playwright import async_api as playwright_api
from unittest.mock import AsyncMock

from backend.app.collectors import zhihu as zhihu_module
from backend.app.collectors.zhihu import (
    BrowserQuestionCapture,
    ZhihuAuthenticationRequired,
    ZhihuCollector,
    ZhihuFetchResult,
    ZhihuVerificationRequired,
    basic_filter_reason,
    browser_page_requires_login,
    browser_verification_signal,
    clean_answer_html,
)
from backend.app.core.config import get_settings


def test_clean_answer_html_preserves_text_links_and_media() -> None:
    plain, markdown, media = clean_answer_html(
        """
        <p>这是一个包含<a href="https://example.com">来源</a>的回答段落。</p>
        <ul><li>第一条建议需要结合具体条件执行。</li></ul>
        <img src="https://pic.example/a.png" alt="示意图">
        <span class="ztext-math" data-tex="x^2+y^2"></span>
        """
    )
    assert "这是一个包含来源的回答段落" in plain
    assert "[来源](https://example.com)" in markdown
    assert media["images"] == ["https://pic.example/a.png"]
    assert media["formulas"] == ["x^2+y^2"]


def test_basic_filter_keeps_short_views_but_marks_empty_and_ads() -> None:
    assert basic_filter_reason("收入压力大，不想买车") == ""
    assert basic_filter_reason("支持") == ""
    assert basic_filter_reason("   ") == "内容为空"
    assert (
        basic_filter_reason(
            "这是一段看似正常但实际用于推广的长内容，加微信获得资料，"
            "扫码咨询可以领取课程，点击购买还有额外优惠。"
        )
        == "疑似广告"
    )


def test_normal_question_copy_does_not_fake_logged_out_state() -> None:
    assert browser_page_requires_login(
        "https://www.zhihu.com/question/58173613"
    ) is False
    assert browser_page_requires_login(
        "https://www.zhihu.com/signin?next=%2Fquestion%2F58173613"
    ) is True


def test_verification_requires_strong_page_signal() -> None:
    normal_copy = (
        "这个问题讨论短信验证码、安全验证产品设计，以及验证码登录的常见流程。"
    )
    assert (
        browser_verification_signal(
            "https://www.zhihu.com/question/58173613",
            normal_copy,
        )
        is None
    )
    assert (
        browser_verification_signal(
            "https://www.zhihu.com/account/unhuman?type=unhuman",
            "",
        )
        == "url:/account/unhuman"
    )
    assert (
        browser_verification_signal(
            "https://www.zhihu.com/question/58173613",
            "您的请求存在异常，请完成安全验证",
        )
        == "text:请完成安全验证"
    )


@pytest.mark.asyncio
async def test_authenticated_auto_mode_uses_browser_before_anonymous_api(
    monkeypatch,
) -> None:
    settings = get_settings().model_copy(
        update={"zhihu_browser_user_data_dir": ""}
    )
    collector = ZhihuCollector(settings)
    expected = ZhihuFetchResult(
        question=None,
        answers=[],
        collector_mode="browser",
    )
    api_fetch = AsyncMock(
        side_effect=AssertionError("不应先请求匿名知乎接口")
    )
    browser_fetch = AsyncMock(return_value=expected)
    monkeypatch.setattr(collector, "_api_json", api_fetch)
    monkeypatch.setattr(
        collector,
        "_browser_question_and_answers",
        browser_fetch,
    )
    monkeypatch.setattr(
        zhihu_module,
        "managed_browser_session_is_authenticated",
        lambda: True,
    )

    result = await collector.fetch_question_and_answers(
        "58173613",
        max_answers=20,
        mode="representative",
        collector_mode="auto",
    )

    assert result is expected
    api_fetch.assert_not_awaited()
    browser_fetch.assert_awaited_once_with("58173613", max_answers=20)


def test_browser_capture_collects_question_and_deduplicates_answer_pages() -> None:
    capture = BrowserQuestionCapture("12345")
    capture.add(
        "/api/v4/questions/12345",
        {"id": "12345", "title": "测试问题"},
    )
    first_answer = {"id": "answer-1", "content": "<p>第一条回答</p>"}
    capture.add(
        "/api/v4/questions/12345/answers",
        {
            "data": [first_answer],
            "paging": {"is_end": False},
        },
    )
    capture.add(
        "/api/v4/questions/12345/answers",
        {
            "data": [first_answer, {"id": "answer-2", "content": "第二条"}],
            "paging": {"is_end": True},
        },
    )

    assert capture.question_payloads[0]["title"] == "测试问题"
    assert [item["id"] for item in capture.raw_answers] == [
        "answer-1",
        "answer-2",
    ]
    assert capture.reached_end is True
    assert (
        basic_filter_reason(
            "先从每天十分钟开始，根据实际体能逐渐增加强度，并记录完成情况形成反馈；"
            "如果某天中断，第二天恢复计划即可，不需要因为一次失败彻底放弃。"
        )
        == ""
    )


@pytest.mark.asyncio
async def test_closed_browser_context_does_not_mask_login_required(
    monkeypatch,
    tmp_path,
) -> None:
    class BodyLocator:
        async def inner_text(self) -> str:
            return "登录后即可查看问题"

    class Page:
        url = "https://www.zhihu.com/signin"

        def on(self, _event: str, _callback) -> None:
            return None

        async def goto(self, *_args, **_kwargs) -> None:
            return None

        async def wait_for_timeout(self, _timeout: int) -> None:
            return None

        def locator(self, _selector: str) -> BodyLocator:
            return BodyLocator()

    class AlreadyClosedContext:
        pages = [Page()]

        async def close(self) -> None:
            raise RuntimeError(
                "Target page, context or browser has been closed"
            )

    context = AlreadyClosedContext()

    class Chromium:
        async def launch_persistent_context(
            self,
            _profile: str,
            *,
            headless: bool,
        ) -> AlreadyClosedContext:
            del headless
            return context

    class Playwright:
        chromium = Chromium()

    class PlaywrightManager:
        async def __aenter__(self) -> Playwright:
            return Playwright()

        async def __aexit__(self, *_args) -> None:
            return None

    class Lease:
        def acquire(self) -> bool:
            return True

        def release(self) -> None:
            return None

    collector = ZhihuCollector(get_settings())
    monkeypatch.setattr(
        collector,
        "_browser_profile",
        lambda: (tmp_path, True),
    )
    monkeypatch.setattr(zhihu_module, "BrowserProfileLease", Lease)
    monkeypatch.setattr(
        zhihu_module,
        "mark_managed_browser_session_invalid",
        lambda: None,
    )
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: PlaywrightManager(),
    )

    with pytest.raises(
        ZhihuAuthenticationRequired,
        match="登录会话已过期",
    ):
        await collector._browser_question_and_answers(
            "12345",
            max_answers=10,
        )


@pytest.mark.asyncio
async def test_verification_pause_keeps_managed_login_marker(
    monkeypatch,
    tmp_path,
) -> None:
    class BodyLocator:
        async def inner_text(self) -> str:
            return "您的请求存在异常，请完成安全验证"

    class Page:
        url = "https://www.zhihu.com/question/58173613"

        def on(self, _event: str, _callback) -> None:
            return None

        async def goto(self, *_args, **_kwargs) -> None:
            return None

        async def wait_for_timeout(self, _timeout: int) -> None:
            return None

        def locator(self, _selector: str) -> BodyLocator:
            return BodyLocator()

    class Context:
        pages = [Page()]

        async def close(self) -> None:
            return None

    class Chromium:
        async def launch_persistent_context(
            self,
            _profile: str,
            *,
            headless: bool,
        ) -> Context:
            del headless
            return Context()

    class Playwright:
        chromium = Chromium()

    class PlaywrightManager:
        async def __aenter__(self) -> Playwright:
            return Playwright()

        async def __aexit__(self, *_args) -> None:
            return None

    class Lease:
        def acquire(self) -> bool:
            return True

        def release(self) -> None:
            return None

    invalidation_calls = 0

    def record_invalidation() -> None:
        nonlocal invalidation_calls
        invalidation_calls += 1

    collector = ZhihuCollector(get_settings())
    monkeypatch.setattr(
        collector,
        "_browser_profile",
        lambda: (tmp_path, True),
    )
    monkeypatch.setattr(zhihu_module, "BrowserProfileLease", Lease)
    monkeypatch.setattr(
        zhihu_module,
        "mark_managed_browser_session_invalid",
        record_invalidation,
    )
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: PlaywrightManager(),
    )

    with pytest.raises(
        ZhihuVerificationRequired,
        match="本次采集被安全验证拦截",
    ):
        await collector._browser_question_and_answers(
            "58173613",
            max_answers=10,
        )

    assert invalidation_calls == 0
