from __future__ import annotations

import asyncio
import hashlib
import html
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from backend.app.core.config import Settings
from backend.app.services.browser_session import (
    BrowserProfileLease,
    close_browser_context_safely,
    managed_browser_profile_path,
    managed_browser_session_is_authenticated,
    mark_managed_browser_session_invalid,
    remove_stale_chromium_profile_locks,
)


class ZhihuCollectorError(RuntimeError):
    """知乎采集器可理解错误。"""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.details = details or {}


class ZhihuAuthenticationRequired(ZhihuCollectorError):
    """需要用户在本地浏览器完成登录。"""


class ZhihuVerificationRequired(ZhihuCollectorError):
    """平台要求人工完成验证码或安全验证。"""


class ZhihuPageChanged(ZhihuCollectorError):
    """页面或接口字段已经变化。"""


def browser_page_requires_login(url: str) -> bool:
    path = urlsplit(url).path.rstrip("/")
    return path == "/signin" or path.startswith("/signin/")


def browser_verification_signal(url: str, page_text: str) -> str | None:
    """只识别验证页强信号，避免问题正文中的普通词语造成误判。"""

    path = urlsplit(url).path.rstrip("/").lower()
    verification_paths = (
        "/account/unhuman",
        "/account/verification",
        "/captcha",
        "/security/verification",
    )
    if any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in verification_paths
    ):
        return f"url:{path}"

    normalized = " ".join(page_text.split())
    strong_phrases = (
        "请完成安全验证",
        "请先完成安全验证",
        "您的请求存在异常",
        "当前请求存在异常",
        "检测到异常行为",
        "访问异常，请稍后重试",
        "暂时限制访问",
    )
    for phrase in strong_phrases:
        if phrase in normalized:
            return f"text:{phrase}"

    if "安全验证" in normalized and any(
        marker in normalized
        for marker in ("完成", "通过", "进行", "请求存在异常", "访问异常")
    ):
        return "text:安全验证组合提示"
    if "暂时限制" in normalized and any(
        marker in normalized for marker in ("访问", "操作", "请求")
    ):
        return "text:暂时限制组合提示"
    return None


async def browser_page_verification_signal(page, page_text: str) -> str | None:
    signal = browser_verification_signal(page.url, page_text)
    if signal:
        return signal

    verification_selectors = (
        "iframe[src*='captcha']",
        "form[action*='unhuman']",
        "[class*='Captcha']:not([class*='Login'])",
        "[class*='Unhuman']",
    )
    for selector in verification_selectors:
        try:
            if await page.locator(selector).first.is_visible():
                return f"selector:{selector}"
        except Exception:
            # 页面正在跳转或测试替身不支持完整 Locator API 时继续检查。
            continue
    return None


@dataclass(slots=True)
class CollectedQuestion:
    external_id: str
    title: str
    url: str
    description: str = ""
    hot_rank: int | None = None
    hot_score: str = ""
    answer_count: int = 0
    follower_count: int = 0
    raw_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CollectedAnswer:
    external_id: str
    author_name: str
    author_url: str
    answer_url: str
    html_content: str
    markdown_content: str
    plain_content: str
    content_hash: str
    vote_count: int
    comment_count: int
    published_at: datetime | None
    updated_at: datetime | None
    sort_order: int
    media: dict[str, list[str]]
    raw_snapshot: dict[str, Any]
    filter_reason: str = ""


@dataclass(slots=True)
class ZhihuFetchResult:
    question: CollectedQuestion | None
    answers: list[CollectedAnswer]
    collector_mode: str
    batch_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    warnings: list[str] = field(default_factory=list)
    capture: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BrowserQuestionCapture:
    question_id: str
    question_payloads: list[dict[str, Any]] = field(default_factory=list)
    raw_answers: list[dict[str, Any]] = field(default_factory=list)
    seen_answer_ids: set[str] = field(default_factory=set)
    reached_end: bool = False

    def add(self, path: str, payload: dict[str, Any]) -> None:
        question_path = f"/api/v4/questions/{self.question_id}"
        if question_path not in path:
            return
        if path.endswith("/answers"):
            data = payload.get("data")
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    answer_id = str(item.get("id") or "")
                    if answer_id and answer_id not in self.seen_answer_ids:
                        self.seen_answer_ids.add(answer_id)
                        self.raw_answers.append(item)
            paging = payload.get("paging")
            if isinstance(paging, dict) and paging.get("is_end") is True:
                self.reached_end = True
        elif path.rstrip("/") == question_path:
            self.question_payloads.append(payload)


class _ZhihuHtmlParser(HTMLParser):
    block_tags = {
        "p",
        "div",
        "section",
        "article",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "br",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.plain_parts: list[str] = []
        self.markdown_parts: list[str] = []
        self.images: list[str] = []
        self.videos: list[str] = []
        self.formulas: list[str] = []
        self._skip_depth = 0
        self._link_stack: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self.block_tags:
            self._newline()
        if tag == "li":
            self.markdown_parts.append("- ")
        elif tag == "blockquote":
            self.markdown_parts.append("> ")
        elif tag in {"h1", "h2", "h3", "h4"}:
            self.markdown_parts.append("#" * int(tag[1]) + " ")
        elif tag == "a":
            self._link_stack.append(attributes.get("href") or "")
            self.markdown_parts.append("[")
        elif tag == "img":
            source = attributes.get("data-original") or attributes.get("src")
            alt = attributes.get("alt") or "图片"
            if source:
                self.images.append(source)
                self.markdown_parts.append(f"![{alt}]({source})")
                self.plain_parts.append(f"[{alt}]")
        elif tag in {"video", "source"}:
            source = attributes.get("src")
            if source:
                self.videos.append(source)
        formula = attributes.get("data-tex") or (
            attributes.get("alt") if "ztext-math" in (attributes.get("class") or "") else None
        )
        if formula:
            self.formulas.append(formula)
            self.markdown_parts.append(f"${formula}$")
            self.plain_parts.append(formula)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "a":
            href = self._link_stack.pop() if self._link_stack else ""
            self.markdown_parts.append(f"]({href})" if href else "]")
        if tag in self.block_tags:
            self._newline()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", html.unescape(data))
        if not text.strip():
            return
        self.plain_parts.append(text)
        self.markdown_parts.append(text)

    def _newline(self) -> None:
        if not self.plain_parts or not self.plain_parts[-1].endswith("\n"):
            self.plain_parts.append("\n")
        if not self.markdown_parts or not self.markdown_parts[-1].endswith("\n"):
            self.markdown_parts.append("\n")

    def result(self) -> tuple[str, str, dict[str, list[str]]]:
        plain = re.sub(r"\n{3,}", "\n\n", "".join(self.plain_parts)).strip()
        markdown = re.sub(
            r"\n{3,}", "\n\n", "".join(self.markdown_parts)
        ).strip()
        return (
            plain,
            markdown,
            {
                "images": list(dict.fromkeys(self.images)),
                "videos": list(dict.fromkeys(self.videos)),
                "formulas": list(dict.fromkeys(self.formulas)),
            },
        )


def clean_answer_html(content: str) -> tuple[str, str, dict[str, list[str]]]:
    parser = _ZhihuHtmlParser()
    parser.feed(content or "")
    parser.close()
    return parser.result()


def basic_filter_reason(plain_content: str) -> str:
    compact = re.sub(r"\s+", "", plain_content)
    if not compact:
        return "内容为空"
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", compact):
        return "仅包含表情或符号"
    advertisement_markers = ("加微信", "扫码咨询", "私信领取", "点击购买")
    if sum(marker in compact for marker in advertisement_markers) >= 2:
        return "疑似广告"
    return ""


def _as_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_answer_payload(payload: dict[str, Any], order: int) -> CollectedAnswer:
    answer_id = str(payload.get("id") or "")
    if not answer_id:
        raise ZhihuPageChanged("知乎回答缺少 answer id")
    content = str(payload.get("content") or "")
    plain, markdown, media = clean_answer_html(content)
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    answer_url = str(payload.get("url") or "")
    question = payload.get("question") if isinstance(payload.get("question"), dict) else {}
    question_id = str(question.get("id") or "")
    if question_id:
        answer_url = f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}"
    elif not answer_url or "api.zhihu.com" in answer_url or "/api/" in answer_url:
        answer_url = f"https://www.zhihu.com/answer/{answer_id}"
    return CollectedAnswer(
        external_id=answer_id,
        author_name=str(author.get("name") or "匿名用户"),
        author_url=str(author.get("url_token") and f"https://www.zhihu.com/people/{author['url_token']}" or ""),
        answer_url=answer_url,
        html_content=content,
        markdown_content=markdown,
        plain_content=plain,
        content_hash=hashlib.sha256(plain.encode("utf-8")).hexdigest(),
        vote_count=_safe_int(payload.get("voteup_count")),
        comment_count=_safe_int(payload.get("comment_count")),
        published_at=_as_datetime(payload.get("created_time")),
        updated_at=_as_datetime(payload.get("updated_time")),
        sort_order=order,
        media=media,
        raw_snapshot=payload,
        filter_reason=basic_filter_reason(plain),
    )


def parse_question_payload(
    payload: dict[str, Any], *, hot_rank: int | None = None, hot_score: str = ""
) -> CollectedQuestion:
    external_id = str(payload.get("id") or "")
    title = str(payload.get("title") or "").strip()
    if not external_id or not title:
        raise ZhihuPageChanged("知乎问题响应缺少 id 或 title")
    detail = str(payload.get("detail") or payload.get("excerpt") or "")
    plain_detail, _, _ = clean_answer_html(detail)
    return CollectedQuestion(
        external_id=external_id,
        title=title,
        url=f"https://www.zhihu.com/question/{external_id}",
        description=plain_detail,
        hot_rank=hot_rank,
        hot_score=hot_score,
        answer_count=_safe_int(payload.get("answer_count")),
        follower_count=_safe_int(payload.get("follower_count")),
        raw_snapshot=payload,
    )


class ZhihuCollector:
    question_include = "title,detail,answer_count,follower_count"
    answer_include = (
        "data[*].id,author.name,author.url_token,voteup_count,comment_count,"
        "content,created_time,updated_time,url,question.id"
    )

    def __init__(self, settings: Settings):
        self.settings = settings
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.zhihu.com/",
        }

    def _browser_profile(self) -> tuple[Path, bool]:
        configured = self.settings.zhihu_browser_user_data_dir.strip()
        managed = not configured
        if managed:
            if not managed_browser_session_is_authenticated():
                raise ZhihuAuthenticationRequired(
                    "知乎需要登录，请在浏览器安全设置页使用知乎 App 扫码登录"
                )
            profile_path = managed_browser_profile_path()
        else:
            profile_path = Path(configured).expanduser().resolve()
        if not profile_path.exists():
            if managed:
                mark_managed_browser_session_invalid()
                raise ZhihuAuthenticationRequired(
                    "工作台知乎登录会话不存在，请重新扫码登录"
                )
            raise ZhihuAuthenticationRequired(
                f"配置的浏览器目录不存在：{profile_path}"
            )
        return profile_path, managed

    async def _api_json(self, url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.settings.ai_request_timeout_seconds,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    response = await client.get(url)
                    text = response.text
                    if response.status_code in {401, 403}:
                        verification_signal = browser_verification_signal(
                            str(response.url),
                            text,
                        )
                        if verification_signal:
                            raise ZhihuVerificationRequired(
                                "知乎已登录会话仍有效，但本次请求需要人工完成安全验证",
                                details={
                                    "source": "api",
                                    "http_status": response.status_code,
                                    "url_path": urlsplit(str(response.url)).path,
                                    "matched_signal": verification_signal,
                                },
                            )
                        raise ZhihuAuthenticationRequired(
                            "知乎接口需要已登录会话，准备切换本地浏览器模式",
                            details={
                                "source": "api",
                                "http_status": response.status_code,
                                "url_path": urlsplit(str(response.url)).path,
                            },
                        )
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ZhihuPageChanged("知乎接口未返回 JSON 对象")
                    return payload
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (2**attempt))
            raise ZhihuCollectorError(f"知乎接口请求失败：{last_error}")

    async def _browser_json(self, *, page_url: str, api_url: str) -> dict[str, Any]:
        profile_path, managed = self._browser_profile()
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ZhihuCollectorError(
                "未安装 Playwright，无法启动工作台浏览器"
            ) from exc

        lease = BrowserProfileLease()
        if not lease.acquire():
            raise ZhihuAuthenticationRequired(
                "工作台浏览器正在用于扫码登录或其他采集任务，请稍后重试"
            )
        context = None
        try:
            if managed:
                remove_stale_chromium_profile_locks(profile_path)
            async with async_playwright() as playwright:
                try:
                    context = await playwright.chromium.launch_persistent_context(
                        str(profile_path),
                        headless=self.settings.playwright_headless,
                    )
                except Exception as exc:
                    raise ZhihuAuthenticationRequired(
                        "无法打开工作台知乎登录会话，请稍后重试或重新扫码登录"
                    ) from exc
                page = (
                    context.pages[0]
                    if context.pages
                    else await context.new_page()
                )
                target_path = urlsplit(api_url).path
                payloads: list[dict[str, Any]] = []
                response_tasks: set[asyncio.Task[None]] = set()

                async def capture_response(response) -> None:
                    if target_path not in urlsplit(response.url).path:
                        return
                    if response.status < 200 or response.status >= 300:
                        return
                    try:
                        payload = await response.json()
                    except Exception:
                        return
                    if isinstance(payload, dict):
                        payloads.append(payload)

                def schedule_capture(response) -> None:
                    task = asyncio.create_task(capture_response(response))
                    response_tasks.add(task)
                    task.add_done_callback(response_tasks.discard)

                page.on("response", schedule_capture)
                await page.goto(
                    page_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                for _ in range(10):
                    await page.wait_for_timeout(1_000)
                    if payloads:
                        break
                    await page.evaluate(
                        "() => window.scrollTo(0, document.body.scrollHeight)"
                    )
                if response_tasks:
                    await asyncio.gather(
                        *response_tasks,
                        return_exceptions=True,
                    )
                page_text = (await page.locator("body").inner_text())[:10_000]
                if browser_page_requires_login(page.url):
                    if managed:
                        mark_managed_browser_session_invalid()
                    raise ZhihuAuthenticationRequired(
                        "知乎登录会话已过期，请重新扫码登录",
                        details={
                            "source": "browser_page",
                            "url_path": urlsplit(page.url).path,
                            "matched_signal": "url:signin",
                        },
                    )
                verification_signal = await browser_page_verification_signal(
                    page,
                    page_text,
                )
                if verification_signal:
                    raise ZhihuVerificationRequired(
                        "知乎已登录会话仍有效，但本次采集被安全验证拦截",
                        details={
                            "source": "browser_page",
                            "url_path": urlsplit(page.url).path,
                            "matched_signal": verification_signal,
                        },
                    )
                if not payloads:
                    raise ZhihuPageChanged(
                        "知乎页面未加载预期数据，页面结构可能已经变化"
                    )
                return payloads[0]
        finally:
            if context is not None:
                await close_browser_context_safely(context)
            lease.release()

    async def _browser_question_and_answers(
        self,
        question_id: str,
        *,
        max_answers: int,
    ) -> ZhihuFetchResult:
        profile_path, managed = self._browser_profile()
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ZhihuCollectorError(
                "未安装 Playwright，无法启动工作台浏览器"
            ) from exc

        lease = BrowserProfileLease()
        if not lease.acquire():
            raise ZhihuAuthenticationRequired(
                "工作台浏览器正在用于扫码登录或其他采集任务，请稍后重试"
            )
        context = None
        try:
            if managed:
                remove_stale_chromium_profile_locks(profile_path)
            async with async_playwright() as playwright:
                try:
                    context = await playwright.chromium.launch_persistent_context(
                        str(profile_path),
                        headless=self.settings.playwright_headless,
                    )
                except Exception as exc:
                    raise ZhihuAuthenticationRequired(
                        "无法打开工作台知乎登录会话，请稍后重试或重新扫码登录"
                    ) from exc
                page = (
                    context.pages[0]
                    if context.pages
                    else await context.new_page()
                )
                page_url = f"https://www.zhihu.com/question/{question_id}"
                capture = BrowserQuestionCapture(question_id)
                response_tasks: set[asyncio.Task[None]] = set()

                async def capture_response(response) -> None:
                    path = urlsplit(response.url).path
                    question_path = f"/api/v4/questions/{question_id}"
                    if question_path not in path:
                        return
                    if response.status < 200 or response.status >= 300:
                        return
                    try:
                        payload = await response.json()
                    except Exception:
                        return
                    if not isinstance(payload, dict):
                        return
                    capture.add(path, payload)

                def schedule_capture(response) -> None:
                    task = asyncio.create_task(capture_response(response))
                    response_tasks.add(task)
                    task.add_done_callback(response_tasks.discard)

                page.on("response", schedule_capture)
                await page.goto(
                    page_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await page.wait_for_timeout(2_000)

                page_text = (await page.locator("body").inner_text())[:10_000]
                if browser_page_requires_login(page.url):
                    if managed:
                        mark_managed_browser_session_invalid()
                    raise ZhihuAuthenticationRequired(
                        "知乎登录会话已过期，请重新扫码登录",
                        details={
                            "source": "browser_page",
                            "url_path": urlsplit(page.url).path,
                            "matched_signal": "url:signin",
                        },
                    )
                verification_signal = await browser_page_verification_signal(
                    page,
                    page_text,
                )
                if verification_signal:
                    raise ZhihuVerificationRequired(
                        "知乎已登录会话仍有效，但本次采集被安全验证拦截",
                        details={
                            "source": "browser_page",
                            "url_path": urlsplit(page.url).path,
                            "matched_signal": verification_signal,
                        },
                    )

                stagnant_rounds = 0
                previous_count = -1
                max_scroll_rounds = max(12, min(80, max_answers * 2))
                for _ in range(max_scroll_rounds):
                    if (
                        len(capture.raw_answers) >= max_answers
                        or capture.reached_end
                    ):
                        break
                    if len(capture.raw_answers) == previous_count:
                        stagnant_rounds += 1
                    else:
                        stagnant_rounds = 0
                        previous_count = len(capture.raw_answers)
                    if stagnant_rounds >= 4:
                        break
                    await page.evaluate(
                        "() => window.scrollTo(0, document.body.scrollHeight)"
                    )
                    await page.mouse.wheel(0, 2_000)
                    await page.wait_for_timeout(1_200)

                if response_tasks:
                    await asyncio.gather(
                        *response_tasks,
                        return_exceptions=True,
                    )

                question = None
                if capture.question_payloads:
                    question = parse_question_payload(
                        capture.question_payloads[-1]
                    )
                else:
                    title_locator = page.locator(
                        "h1.QuestionHeader-title, h1"
                    ).first
                    title = (
                        (await title_locator.inner_text()).strip()
                        if await title_locator.is_visible()
                        else ""
                    )
                    if title:
                        question = CollectedQuestion(
                            external_id=question_id,
                            title=title,
                            url=page_url,
                            raw_snapshot={"source": "browser_dom"},
                        )
                if not question:
                    raise ZhihuPageChanged(
                        "知乎页面未加载问题信息，页面结构可能已经变化"
                    )

                answers: list[CollectedAnswer] = []
                seen_hashes: set[str] = set()
                for raw in capture.raw_answers:
                    answer = parse_answer_payload(raw, len(answers))
                    if answer.content_hash in seen_hashes:
                        continue
                    seen_hashes.add(answer.content_hash)
                    answers.append(answer)
                    if len(answers) >= max_answers:
                        break
                return ZhihuFetchResult(
                    question=question,
                    answers=answers,
                    collector_mode="browser",
                    warnings=[],
                )
        finally:
            try:
                if context is not None:
                    await close_browser_context_safely(context)
            finally:
                lease.release()

    async def _json(
        self,
        *,
        api_url: str,
        page_url: str,
        collector_mode: Literal["auto", "api", "browser"],
    ) -> tuple[dict[str, Any], str, list[str]]:
        warnings: list[str] = []
        managed_session_ready = (
            collector_mode == "auto"
            and not self.settings.zhihu_browser_user_data_dir.strip()
            and managed_browser_session_is_authenticated()
        )
        if managed_session_ready:
            payload = await self._browser_json(
                page_url=page_url,
                api_url=api_url,
            )
            return payload, "browser", warnings
        if collector_mode in {"auto", "api"}:
            try:
                return await self._api_json(api_url), "api", warnings
            except (ZhihuAuthenticationRequired, ZhihuVerificationRequired) as exc:
                if collector_mode == "api":
                    raise
                warnings.append(str(exc))
        payload = await self._browser_json(page_url=page_url, api_url=api_url)
        return payload, "browser", warnings

    async def fetch_question_and_answers(
        self,
        question_id: str,
        *,
        max_answers: int,
        mode: Literal["representative", "complete"],
        collector_mode: Literal["auto", "api", "browser"] = "auto",
    ) -> ZhihuFetchResult:
        managed_session_ready = (
            collector_mode == "auto"
            and not self.settings.zhihu_browser_user_data_dir.strip()
            and managed_browser_session_is_authenticated()
        )
        if collector_mode == "browser" or managed_session_ready:
            return await self._browser_question_and_answers(
                question_id,
                max_answers=max_answers,
            )

        page_url = f"https://www.zhihu.com/question/{question_id}"
        question_api = (
            f"https://www.zhihu.com/api/v4/questions/{question_id}"
            f"?include={self.question_include}"
        )
        warnings: list[str] = []
        try:
            question_payload = await self._api_json(question_api)
            used_mode = "api"
        except (ZhihuAuthenticationRequired, ZhihuVerificationRequired) as exc:
            if collector_mode == "api":
                raise
            warnings.append(str(exc))
            result = await self._browser_question_and_answers(
                question_id,
                max_answers=max_answers,
            )
            result.warnings = warnings
            return result
        question = parse_question_payload(question_payload)
        answers: list[CollectedAnswer] = []
        offset = 0
        page_size = min(20, max_answers)
        sort_by = "default" if mode == "representative" else "updated"
        seen_ids: set[str] = set()
        seen_hashes: set[str] = set()
        while len(answers) < max_answers:
            limit = min(page_size, max_answers - len(answers))
            api_url = (
                f"https://www.zhihu.com/api/v4/questions/{question_id}/answers"
                f"?include={self.answer_include}&limit={limit}&offset={offset}"
                f"&sort_by={sort_by}"
            )
            try:
                payload = await self._api_json(api_url)
            except (
                ZhihuAuthenticationRequired,
                ZhihuVerificationRequired,
            ) as exc:
                if collector_mode == "api":
                    raise
                warnings.append(str(exc))
                result = await self._browser_question_and_answers(
                    question_id,
                    max_answers=max_answers,
                )
                result.warnings = list(dict.fromkeys(warnings))
                return result
            data = payload.get("data")
            if not isinstance(data, list):
                raise ZhihuPageChanged("知乎回答响应缺少 data 列表")
            if not data:
                break
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                answer = parse_answer_payload(raw, len(answers))
                if answer.external_id in seen_ids or answer.content_hash in seen_hashes:
                    continue
                seen_ids.add(answer.external_id)
                seen_hashes.add(answer.content_hash)
                answers.append(answer)
                if len(answers) >= max_answers:
                    break
            paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
            if paging.get("is_end") is True or len(data) < limit:
                break
            offset += len(data)
        return ZhihuFetchResult(
            question=question,
            answers=answers,
            collector_mode=used_mode,
            warnings=warnings,
        )

    async def fetch_hot_questions(
        self,
        *,
        limit: int,
        collector_mode: Literal["auto", "api", "browser"] = "auto",
    ) -> tuple[list[CollectedQuestion], str, list[str]]:
        api_url = (
            "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
            f"?limit={limit}"
        )
        payload, used_mode, warnings = await self._json(
            api_url=api_url,
            page_url="https://www.zhihu.com/hot",
            collector_mode=collector_mode,
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise ZhihuPageChanged("知乎热榜响应缺少 data 列表")
        questions: list[CollectedQuestion] = []
        for index, item in enumerate(data[:limit], start=1):
            if not isinstance(item, dict):
                continue
            target = item.get("target") if isinstance(item.get("target"), dict) else {}
            detail_text = str(item.get("detail_text") or item.get("detail_text_v2") or "")
            try:
                questions.append(
                    parse_question_payload(
                        target,
                        hot_rank=index,
                        hot_score=detail_text,
                    )
                )
            except ZhihuPageChanged:
                continue
        return questions, used_mode, warnings
