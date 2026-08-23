from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.services.claim_extractor import DEFAULT_SYSTEM_PROMPT
from backend.app.ai.services.content import (
    ARTICLE_SYSTEM_PROMPT,
    CLAIM_SYSTEM_PROMPT,
    CLUSTER_SYSTEM_PROMPT,
    INFOGRAPHIC_SYSTEM_PROMPT,
    OPINION_MAP_SYSTEM_PROMPT,
    QUALITY_SYSTEM_PROMPT,
    REVIEW_SYSTEM_PROMPT,
    REWRITE_SYSTEM_PROMPT,
)
from backend.app.core.config import get_settings
from backend.app.models.core import (
    OpenSourceReference,
    PromptTemplate,
    PromptVersion,
    SystemSetting,
)
from backend.app.models.media import ImageTemplate
from backend.app.services.settings import SETTING_DEFAULTS


OPEN_SOURCE_REFERENCES = (
    (
        "FastAPI",
        "MIT",
        "https://github.com/fastapi/fastapi",
        "第一阶段后端 Web 框架。",
    ),
    (
        "React",
        "MIT",
        "https://github.com/facebook/react",
        "第一阶段前端视图层。",
    ),
    (
        "Ant Design",
        "MIT",
        "https://github.com/ant-design/ant-design",
        "第一阶段单一 UI 组件库。",
    ),
    (
        "Redis",
        "RSALv2/SSPLv1",
        "https://github.com/redis/redis",
        "第一阶段队列、临时状态和 Pub/Sub；使用官方容器镜像。",
    ),
    (
        "Microsoft Playwright",
        "Apache-2.0",
        "https://github.com/microsoft/playwright",
        "仅用于信息图 PNG 渲染；知乎采集不再使用独立 Playwright 浏览器。",
    ),
    (
        "Pillow",
        "MIT-CMU",
        "https://github.com/python-pillow/Pillow",
        "第三阶段仅用于为用户上传的背景原图生成本地缩略图。",
    ),
    (
        "OpenBiliClaw",
        "MIT",
        "https://github.com/whiteguo233/OpenBiliClaw",
        "仅借鉴扩展任务下发、同源 credentials 请求、不导出 Cookie 和扩展 E2E 的架构；本项目自行实现，未复制代码。",
    ),
    (
        "RSSHub 知乎路由",
        "AGPL-3.0",
        "https://github.com/DIYgod/RSSHub/tree/master/lib/routes/zhihu",
        "仅参考回答分页、Cookie 有效性检查和接口集中封装行为；未复制或引入 AGPL 代码。",
    ),
    (
        "zhihu-hot-hub",
        "MIT",
        "https://github.com/SnailDev/zhihu-hot-hub",
        "仅作为未来知乎热榜种子和归档来源研究，不用于回答采集。",
    ),
    (
        "Zhihu++",
        "AGPL-3.0",
        "https://github.com/zly2006/zhihu-plus-plus",
        "仅研究活跃知乎客户端的内容模型和登录体验；未复制或引入 AGPL 代码。",
    ),
)

OPEN_SOURCE_REFERENCE_VERSIONS = {
    "Microsoft Playwright": "1.61.0",
    "OpenBiliClaw": "f001c1f899645a6139995e7d7b047510d9e3a3a5",
    "RSSHub 知乎路由": "5151c3233bc7bacfaecc6e4f01aba2b60022d683",
    "zhihu-hot-hub": "ec324e653c03a7127d63134bb052dbc46dce38de",
    "Zhihu++": "80a097116a069b00a0c4b2bdaee7a944551820fb",
}


PHASE_TWO_PROMPTS = (
    (
        "answer_quality_evaluation",
        "回答质量筛选",
        "第二阶段批量回答相关性、质量和信息密度筛选。",
        QUALITY_SYSTEM_PROMPT,
        ["question_title", "answers"],
        "fast_text_model",
    ),
    (
        "answer_claim_batch_extraction",
        "批量回答观点提取",
        "第二阶段保留 answer_id 的结构化观点提取。",
        CLAIM_SYSTEM_PROMPT,
        ["question_title", "answers"],
        "fast_text_model",
    ),
    (
        "claim_cluster_refinement",
        "观点聚类修正",
        "第二阶段粗聚类合并、拆分、命名和立场识别。",
        CLUSTER_SYSTEM_PROMPT,
        ["question_title", "rough_clusters"],
        "reasoning_model",
    ),
    (
        "opinion_map_generation",
        "观点地图生成",
        "第二阶段共识、分歧、条件、风险和建议整理。",
        OPINION_MAP_SYSTEM_PROMPT,
        ["question_title", "clusters"],
        "reasoning_model",
    ),
    (
        "article_generation",
        "总结文章生成",
        "第二阶段文章和段落来源映射生成。",
        ARTICLE_SYSTEM_PROMPT,
        ["question_title", "opinion_map", "clusters"],
        "reasoning_model",
    ),
    (
        "article_quality_review",
        "文章独立质量审核",
        "第二阶段与生成分离的内容质量和高风险审核。",
        REVIEW_SYSTEM_PROMPT,
        ["question_title", "article", "opinion_map"],
        "reasoning_model",
    ),
)


PHASE_THREE_PROMPTS = (
    (
        "infographic_content_generation",
        "信息图文案生成",
        "第三阶段将观点地图压缩为有长度限制的中文信息图 JSON。",
        INFOGRAPHIC_SYSTEM_PROMPT,
        ["question_title", "opinion_map", "clusters", "template_type"],
        "fast_text_model",
    ),
    (
        "draft_rewrite",
        "草稿局部改写",
        "第三阶段草稿审核中的段落或选中文本改写。",
        REWRITE_SYSTEM_PROMPT,
        ["question_title", "scope", "text", "instruction"],
        "fast_text_model",
    ),
)


IMAGE_TEMPLATES = (
    (
        "知识总结卡",
        "knowledge_card",
        {
            "description": "适合一般知识总结，突出一句话结论、共识、条件和建议。",
            "canvas_sizes": ["1080x1440", "1242x1660"],
            "reserved": False,
        },
    ),
    (
        "观点对比表",
        "comparison_table",
        {
            "description": "适合支持/反对、A/B 或存在明显分歧的问题。",
            "canvas_sizes": ["1080x1440", "1242x1660"],
            "reserved": False,
        },
    ),
)


async def seed_defaults(session: AsyncSession) -> None:
    defaults = {**SETTING_DEFAULTS, "provider_mode": get_settings().ai_provider_mode}
    for key, value in defaults.items():
        if not await session.get(SystemSetting, key):
            session.add(SystemSetting(key=key, value=value, is_secret=False))

    prompt = await session.scalar(
        select(PromptTemplate).where(PromptTemplate.key == "answer_claim_extraction")
    )
    if not prompt:
        prompt = PromptTemplate(
            key="answer_claim_extraction",
            name="回答观点提取",
            description="第一阶段结构化观点提取 Prompt。",
            active_version=1,
        )
        session.add(prompt)
        await session.flush()
        session.add(
            PromptVersion(
                template_id=prompt.id,
                version=1,
                content=DEFAULT_SYSTEM_PROMPT,
                variables=["question_title", "answer_text"],
                model_role="fast_text_model",
                is_active=True,
            )
        )

    for key, name, description, content, variables, model_role in (
        *PHASE_TWO_PROMPTS,
        *PHASE_THREE_PROMPTS,
    ):
        existing = await session.scalar(
            select(PromptTemplate).where(PromptTemplate.key == key)
        )
        if existing:
            continue
        template = PromptTemplate(
            key=key,
            name=name,
            description=description,
            active_version=1,
        )
        session.add(template)
        await session.flush()
        session.add(
            PromptVersion(
                template_id=template.id,
                version=1,
                content=content,
                variables=variables,
                model_role=model_role,
                is_active=True,
            )
        )

    existing_template_types = set(
        (
            await session.scalars(
                select(ImageTemplate.template_type).where(
                    ImageTemplate.template_type.in_(
                        [item[1] for item in IMAGE_TEMPLATES]
                    )
                )
            )
        ).all()
    )
    for name, template_type, schema_json in IMAGE_TEMPLATES:
        if template_type not in existing_template_types:
            session.add(
                ImageTemplate(
                    name=name,
                    template_type=template_type,
                    schema_json=schema_json,
                    enabled=True,
                )
            )

    existing_references = {
        item.name: item
        for item in (
            await session.scalars(
                select(OpenSourceReference).where(
                    OpenSourceReference.name.in_(
                        [item[0] for item in OPEN_SOURCE_REFERENCES]
                    )
                )
            )
        ).all()
    }
    for name, license_name, source_url, usage_note in OPEN_SOURCE_REFERENCES:
        existing = existing_references.get(name)
        if existing:
            existing.version = OPEN_SOURCE_REFERENCE_VERSIONS.get(
                name, existing.version
            )
            existing.license_name = license_name
            existing.source_url = source_url
            existing.usage_note = usage_note
        else:
            session.add(
                OpenSourceReference(
                    name=name,
                    version=OPEN_SOURCE_REFERENCE_VERSIONS.get(
                        name, "not-pinned"
                    ),
                    license_name=license_name,
                    source_url=source_url,
                    usage_note=usage_note,
                )
            )
    await session.commit()
