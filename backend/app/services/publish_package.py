"""Downloadable, version-bound artifacts. This module never contacts Zhihu."""
from __future__ import annotations

from html import escape
import hashlib
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED

from backend.app.models.core import ArticleVersion
from backend.app.models.media import ImageVersion
from backend.app.services.image_workflow import resolve_rendered_path
from backend.app.services.publishing import publish_readiness


async def build_publish_package(session, draft) -> bytes:
    readiness = await publish_readiness(session, draft)
    if not readiness.ready:
        raise ValueError("；".join(readiness.blockers))
    article = await session.get(ArticleVersion, readiness.article_version_id)
    image = await session.get(ImageVersion, readiness.image_version_id)
    png = resolve_rendered_path(image).read_bytes()
    files = {
        "article.md": (f"# {article.title}\n\n{article.content}\n").encode("utf-8"),
        "article.html": ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>body{max-width:780px;margin:32px auto;padding:20px;font:18px/1.8 sans-serif}article{white-space:pre-wrap}img{max-width:100%}</style>"
            f"<title>{escape(article.title)}</title><h1>{escape(article.title)}</h1>"
            f"<article>{escape(article.content)}</article><img src='infographic.png' alt='总结信息图'></html>").encode("utf-8"),
        "infographic.png": png,
        "sources.json": json.dumps(article.source_snapshot or {}, ensure_ascii=False, indent=2).encode("utf-8"),
    }
    manifest = {"format": "zhihu-publish-package-v1", "draft_id": draft.id,
        "article_version_id": article.id, "article_version": article.version,
        "image_version_id": image.id, "image_version": image.version,
        "publishing": "manual", "warnings": readiness.warnings,
        "sources_require_recheck": bool((article.source_snapshot or {}).get("edited")),
        "sha256": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}}
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()
