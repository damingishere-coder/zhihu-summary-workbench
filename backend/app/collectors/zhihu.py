from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal

import httpx

from backend.app.core.config import Settings


class ZhihuCollectorError(RuntimeError):
    """知乎采集器可理解错误。"""


class ZhihuAuthenticationRequired(ZhihuCollectorError):
    """需要用户在本地浏览器完成登录。"""


class ZhihuVerificationRequired(ZhihuCollectorError):
    """平台要求人工完成验证码或安全验证。"""


class ZhihuPageChanged(ZhihuCollectorError):
    """页面或接口字段已经变化。"""


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
    if len(compact) < 40:
        return "内容过短"
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
                        if any(marker in text for marker in ("验证码", "安全验证", "访问异常")):
                            raise ZhihuVerificationRequired(
                                "知乎要求人工完成安全验证，采集任务已暂停"
                            )
                        raise ZhihuAuthenticationRequired(
                            "知乎接口需要已登录会话，准备切换本地浏览器模式"
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
        profile = self.settings.zhihu_browser_user_data_dir.strip()
        if not profile:
            raise ZhihuAuthenticationRequired(
                "接口模式不可用，且未配置知乎本地浏览器目录；请先在设置页配置已登录的 Chrome 用户数据目录"
            )
        profile_path = Path(profile).expanduser().resolve()
        if not profile_path.exists():
            raise ZhihuAuthenticationRequired(
                f"配置的浏览器目录不存在：{profile_path}"
            )
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ZhihuCollectorError(
                "未安装 Playwright；请安装后运行 playwright install chrome"
            ) from exc

        async with async_playwright() as playwright:
            try:
                context = await playwright.chromium.launch_persistent_context(
                    str(profile_path),
                    channel="chrome",
                    headless=self.settings.playwright_headless,
                )
            except Exception as exc:
                raise ZhihuAuthenticationRequired(
                    "无法打开本地 Chrome 登录会话；请关闭占用该用户目录的 Chrome 窗口后重试"
                ) from exc
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(page_url, wait_until="domcontentloaded", timeout=60_000)
                page_text = (await page.locator("body").inner_text())[:10_000]
                if any(marker in page_text for marker in ("验证码", "安全验证", "登录后")):
                    raise ZhihuVerificationRequired(
                        "知乎页面要求登录或人工安全验证，采集任务已暂停"
                    )
                result = await page.evaluate(
                    """async (url) => {
                      const response = await fetch(url, {
                        credentials: "include",
                        headers: {"Accept": "application/json, text/plain, */*"}
                      });
                      return {status: response.status, text: await response.text()};
                    }""",
                    api_url,
                )
                status = int(result.get("status", 0))
                text = str(result.get("text", ""))
                if status in {401, 403}:
                    raise ZhihuVerificationRequired(
                        "本地浏览器会话未通过知乎验证，采集任务已暂停"
                    )
                if status < 200 or status >= 300:
                    raise ZhihuCollectorError(f"知乎浏览器请求失败（HTTP {status}）")
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    raise ZhihuPageChanged("知乎浏览器响应未返回 JSON 对象")
                return payload
            finally:
                await context.close()

    async def _json(
        self,
        *,
        api_url: str,
        page_url: str,
        collector_mode: Literal["auto", "api", "browser"],
    ) -> tuple[dict[str, Any], str, list[str]]:
        warnings: list[str] = []
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
        page_url = f"https://www.zhihu.com/question/{question_id}"
        question_api = (
            f"https://www.zhihu.com/api/v4/questions/{question_id}"
            f"?include={self.question_include}"
        )
        question_payload, used_mode, warnings = await self._json(
            api_url=question_api,
            page_url=page_url,
            collector_mode=collector_mode,
        )
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
            payload, page_mode, page_warnings = await self._json(
                api_url=api_url,
                page_url=page_url,
                collector_mode="browser" if used_mode == "browser" else collector_mode,
            )
            if page_mode == "browser":
                used_mode = "browser"
            warnings.extend(item for item in page_warnings if item not in warnings)
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
