from __future__ import annotations

import base64
import html
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, async_playwright
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import REPOSITORY_ROOT, Settings
from backend.app.models.media import ImageDraft, ImageVersion
from backend.app.schemas.image import InfographicContentData
from backend.app.services.image_workflow import (
    resolve_background_path,
    workspace_to_read,
)


def _text(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _list_items(values: list[object], field: str) -> str:
    return "".join(
        f'<li class="safe-text" data-field="{_text(field)}">{_text(value)}</li>'
        for value in values
    )


def _knowledge_card(content: InfographicContentData) -> str:
    consensus = "".join(
        (
            '<article class="point">'
            f'<h3 class="safe-text" data-field="共识标题">{_text(item.title)}</h3>'
            f'<p class="safe-text" data-field="共识说明">{_text(item.description)}</p>'
            "</article>"
        )
        for item in content.consensus
    )
    sections: list[str] = []
    for title, values, field in (
        ("主要分歧", content.disagreements, "主要分歧"),
        ("适用条件", content.conditions, "适用条件"),
        ("行动建议", content.suggestions, "行动建议"),
    ):
        if values:
            sections.append(
                '<section class="detail-block">'
                f"<h2>{_text(title)}</h2>"
                f"<ul>{_list_items(list(values), field)}</ul>"
                "</section>"
            )
    return (
        '<section class="consensus-block">'
        "<h2>大家较一致的判断</h2>"
        f'<div class="point-grid">{consensus}</div>'
        "</section>"
        f'<div class="detail-grid">{"".join(sections)}</div>'
    )


def _comparison_table(content: InfographicContentData) -> str:
    left = "".join(
        (
            '<article class="compare-item">'
            f'<h3 class="safe-text" data-field="共识标题">{_text(item.title)}</h3>'
            f'<p class="safe-text" data-field="共识说明">{_text(item.description)}</p>'
            "</article>"
        )
        for item in content.consensus
    )
    right = "".join(
        f'<article class="compare-item"><p class="safe-text" '
        f'data-field="主要分歧">{_text(item)}</p></article>'
        for item in content.disagreements
    )
    left_content = left or '<p class="muted">暂无共同判断</p>'
    right_content = right or '<p class="muted">暂无明显分歧</p>'
    return (
        '<section class="comparison">'
        '<div class="comparison-column comparison-column--left">'
        "<h2>共同判断</h2>"
        f"{left_content}"
        "</div>"
        '<div class="comparison-column comparison-column--right">'
        "<h2>主要分歧</h2>"
        f"{right_content}"
        "</div>"
        "</section>"
        '<section class="comparison-footer">'
        '<div><h2>适用条件</h2><ul>'
        f"{_list_items(list(content.conditions), '适用条件')}"
        "</ul></div>"
        '<div><h2>行动建议</h2><ul>'
        f"{_list_items(list(content.suggestions), '行动建议')}"
        "</ul></div>"
        "</section>"
    )


def _background_data(version: ImageVersion, use_css: bool) -> str:
    if use_css or not version.background_path or version.background_deleted:
        return ""
    path = resolve_background_path(version)
    mime = version.content_type or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_infographic_html(
    image_draft: ImageDraft, version: ImageVersion
) -> str:
    if version.content_json.get('opinion_survey'):
        from backend.app.services.survey_chart import survey_chart_html
        return survey_chart_html(version.content_json, version.canvas_width, version.canvas_height)
    content = InfographicContentData.model_validate(version.content_json)
    template_type = str(
        version.content_json.get("template_type") or "knowledge_card"
    )
    font_scale = float(version.content_json.get("font_scale") or 1)
    brand_name = _text(
        version.content_json.get("brand_name") or "知乎问题总结工作台"
    )
    footer_text = _text(
        version.content_json.get("footer_text")
        or "内容由 AI 辅助整理，请结合来源人工核验"
    )
    position_x = int(version.content_json.get("background_position_x") or 50)
    position_y = int(version.content_json.get("background_position_y") or 50)
    background_scale = float(version.content_json.get("background_scale") or 1)
    use_css = bool(
        version.content_json.get(
            "use_css_background", image_draft.use_css_background
        )
    )
    background = _background_data(version, use_css)
    body = (
        _comparison_table(content)
        if template_type == "comparison_table"
        else _knowledge_card(content)
    )
    background_css = (
        f"background-image:url('{background}');"
        f"background-position:{position_x}% {position_y}%;"
        f"background-size:{background_scale * 100:.0f}%;"
        if background
        else "background-color:#f5f7fa;"
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; width: 100%; height: 100%; }}
body {{
  color: #172033;
  font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  font-size: calc(26px * {font_scale});
  background: #f5f7fa;
}}
.canvas {{
  position: relative;
  width: {version.canvas_width}px;
  height: {version.canvas_height}px;
  overflow: hidden;
  {background_css}
  background-repeat: no-repeat;
}}
.canvas::before {{
  content: "";
  position: absolute;
  inset: 0;
  background: rgba(247, 249, 252, {0.86 if background else 0});
}}
.content {{
  position: relative;
  z-index: 1;
  height: 100%;
  padding: 68px 72px 54px;
  display: flex;
  flex-direction: column;
  gap: 26px;
}}
.masthead {{
  border-top: 10px solid #1769e0;
  padding-top: 28px;
}}
.brand {{
  color: #1769e0;
  font-size: calc(22px * {font_scale});
  font-weight: 700;
  letter-spacing: .06em;
}}
h1 {{
  margin: 18px 0 16px;
  max-height: calc(184px * {font_scale});
  overflow: hidden;
  font-size: calc(60px * {font_scale});
  line-height: 1.5;
  letter-spacing: -.03em;
}}
.conclusion {{
  margin: 0;
  padding: 24px 28px;
  max-height: calc(158px * {font_scale});
  overflow: hidden;
  color: #123a72;
  background: #e9f2ff;
  border-left: 8px solid #1769e0;
  font-size: calc(35px * {font_scale});
  font-weight: 650;
  line-height: 1.42;
}}
h2 {{
  margin: 0 0 16px;
  color: #153b6b;
  font-size: calc(29px * {font_scale});
  line-height: 1.3;
}}
h3 {{
  margin: 0 0 10px;
  color: #172033;
  font-size: calc(27px * {font_scale});
  line-height: 1.34;
}}
p, li {{
  margin: 0;
  font-size: calc(24px * {font_scale});
  line-height: 1.55;
}}
.consensus-block, .detail-block, .comparison-column, .comparison-footer > div {{
  background: rgba(255, 255, 255, .94);
  border: 2px solid #dce3ec;
  padding: 24px 26px;
}}
.point-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}}
.point {{
  min-height: 154px;
  padding: 18px;
  background: #f2f6fb;
  border-left: 5px solid #15805d;
}}
.point p {{
  max-height: calc(114px * {font_scale});
  overflow: hidden;
}}
.detail-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}}
.detail-block {{
  min-height: 245px;
}}
ul {{
  margin: 0;
  padding-left: 1.15em;
}}
li {{
  margin-bottom: 10px;
  max-height: calc(112px * {font_scale});
  overflow: hidden;
}}
.comparison {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  min-height: 610px;
}}
.comparison-column--left {{ border-top: 8px solid #15805d; }}
.comparison-column--right {{ border-top: 8px solid #c76b16; }}
.compare-item {{
  margin-bottom: 18px;
  padding: 17px;
  background: #f5f7fa;
  border: 1px solid #dce3ec;
}}
.compare-item p {{
  max-height: calc(124px * {font_scale});
  overflow: hidden;
}}
.comparison-footer {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}}
.muted {{ color: #667085; }}
.footer {{
  margin-top: auto;
  display: flex;
  justify-content: space-between;
  gap: 24px;
  border-top: 2px solid #dce3ec;
  padding-top: 18px;
  color: #667085;
  font-size: calc(19px * {font_scale});
}}
{'.safe-text {max-height:none!important;} .content > * {flex-shrink:0;}' if version.content_json.get('auto_fit') else ''}
</style>
</head>
<body>
  <main class="canvas" data-template="{_text(template_type)}">
    <div class="content">
      <header class="masthead">
        <div class="brand">{brand_name}</div>
        <h1 class="safe-text" data-field="标题">{_text(content.title)}</h1>
        <p class="conclusion safe-text" data-field="一句话结论">{_text(content.one_line_conclusion)}</p>
      </header>
      {body}
      <footer class="footer">
        <span>{footer_text}</span>
        <span>来源观点簇 {len(content.source_cluster_ids)} 个</span>
      </footer>
    </div>
  </main>
</body>
</html>"""


async def _launch_browser(playwright) -> Browser:
    errors: list[str] = []
    for executable in _system_chrome_candidates():
        try:
            return await playwright.chromium.launch(
                executable_path=str(executable), headless=True
            )
        except Exception as exc:
            errors.append(f"{executable}: {exc}")
    bundled = Path(playwright.chromium.executable_path)
    if bundled.is_file():
        try:
            return await playwright.chromium.launch(headless=True)
        except Exception as exc:
            errors.append(f"{bundled}: {exc}")
    raise RuntimeError(
        "信息图渲染浏览器不可用；未找到可启动的系统 Chrome 或匹配当前 Playwright 的 Chromium。"
        + (f" 探测详情：{' | '.join(errors)}" if errors else "")
    )


def _system_chrome_candidates() -> list[Path]:
    candidates: list[Path] = []
    for executable in ("chrome", "google-chrome", "google-chrome-stable"):
        resolved = shutil.which(executable)
        if resolved:
            candidates.append(Path(resolved))
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(
                Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            )
    return list(
        dict.fromkeys(path.resolve() for path in candidates if path.is_file())
    )


async def render_infographic(
    session: AsyncSession,
    image_draft: ImageDraft,
    version: ImageVersion,
    settings: Settings,
) -> None:
    if version.content_json.get('opinion_survey'):
        rows = version.content_json['opinion_survey']['rows'][:8]
        version.canvas_height = max(version.canvas_height, 1100 + len(rows) * 185)
    html_payload = build_infographic_html(image_draft, version)
    folder = (
        REPOSITORY_ROOT
        / "data"
        / "rendered"
        / "images"
        / image_draft.article_draft_id
    ).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    html_path = folder / f"v{version.version}-{version.id}.html"
    png_path = folder / f"v{version.version}-{version.id}.png"
    html_path.write_text(html_payload, encoding="utf-8")
    version.html_snapshot_path = str(html_path)
    version.render_status = "rendering"
    logs: list[dict[str, Any]] = [
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "level": "info",
            "message": (
                f"开始以 {version.canvas_width}×{version.canvas_height} 固定视口渲染"
            ),
        }
    ]
    await session.commit()

    last_error: Exception | None = None
    for attempt in range(1, max(1, settings.infographic_render_attempts) + 1):
        try:
            async with async_playwright() as playwright:
                browser = await _launch_browser(playwright)
                page = await browser.new_page(
                    viewport={
                        "width": version.canvas_width,
                        "height": version.canvas_height,
                    },
                    device_scale_factor=1,
                )
                try:
                    await page.set_content(html_payload, wait_until="networkidle")
                    await page.evaluate("document.fonts.ready")
                    await page.wait_for_function(
                        "() => Array.from(document.images).every((img) => img.complete)"
                    )
                    overflow = await page.eval_on_selector_all(
                        ".safe-text",
                        """elements => elements
                          .filter((item) =>
                            item.scrollHeight > item.clientHeight + 1 ||
                            item.scrollWidth > item.clientWidth + 1)
                          .map((item) => ({
                            field: item.dataset.field || "未知字段",
                            text: (item.textContent || "").slice(0, 120),
                            scrollHeight: item.scrollHeight,
                            clientHeight: item.clientHeight,
                            scrollWidth: item.scrollWidth,
                            clientWidth: item.clientWidth,
                          }))""",
                    )
                    boundary_overflow = await page.eval_on_selector_all(
                        ".safe-text, .footer",
                        """elements => elements.filter(item => {
                          const box = item.getBoundingClientRect();
                          const canvas = document.querySelector('.canvas').getBoundingClientRect();
                          return box.bottom > canvas.bottom - 12 || box.right > canvas.right || box.left < canvas.left;
                        }).map(item => ({field: item.dataset.field || '画布边界', text: (item.textContent || '').slice(0,120)}))""",
                    )
                    overflow.extend(boundary_overflow)
                    if overflow:
                        version.overflow_json = overflow
                        version.render_status = "overflow"
                        logs.append(
                            {
                                "at": datetime.now(timezone.utc).isoformat(),
                                "level": "error",
                                "message": f"检测到 {len(overflow)} 处文字溢出",
                            }
                        )
                        version.render_log_json = logs
                        await session.commit()
                        raise ValueError(
                            "检测到文字溢出，请精简提示字段或降低字号后重试"
                        )
                    await page.screenshot(
                        path=str(png_path),
                        full_page=False,
                        animations="disabled",
                    )
                finally:
                    await browser.close()
            version.rendered_path = str(png_path)
            version.render_status = "rendered"
            version.overflow_json = []
            logs.append(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "level": "info",
                    "message": f"第 {attempt} 次渲染成功，PNG 已保存",
                }
            )
            version.render_log_json = logs
            image_draft.status = "rendered"
            await session.commit()
            return
        except ValueError:
            raise
        except Exception as exc:
            last_error = exc
            logs.append(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "level": "warning",
                    "message": f"第 {attempt} 次渲染失败：{exc}",
                }
            )
    version.render_status = "failed"
    version.render_log_json = logs
    image_draft.status = "render_failed"
    await session.commit()
    raise RuntimeError(f"信息图渲染失败：{last_error}")


async def render_image_workspace(
    session: AsyncSession,
    image_draft: ImageDraft,
    settings: Settings,
    *,
    version_number: int | None = None,
):
    target_number = version_number or image_draft.current_version
    version = await session.scalar(
        select(ImageVersion).where(
            ImageVersion.image_draft_id == image_draft.id,
            ImageVersion.version == target_number,
        )
    )
    if not version:
        raise ValueError("要渲染的图片版本不存在")
    await render_infographic(session, image_draft, version, settings)
    return await workspace_to_read(session, image_draft)
