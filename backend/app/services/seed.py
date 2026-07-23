from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.services.claim_extractor import DEFAULT_SYSTEM_PROMPT
from backend.app.ai.services.content import (
    ARTICLE_SYSTEM_PROMPT,
    CLAIM_SYSTEM_PROMPT,
    CLUSTER_SYSTEM_PROMPT,
    OPINION_MAP_SYSTEM_PROMPT,
    QUALITY_SYSTEM_PROMPT,
    REVIEW_SYSTEM_PROMPT,
)
from backend.app.models.core import (
    OpenSourceReference,
    PromptTemplate,
    PromptVersion,
    SystemSetting,
)
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
        "第二阶段使用用户本地已登录 Chrome 会话作为知乎采集安全降级模式。",
    ),
)


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


async def seed_defaults(session: AsyncSession) -> None:
    for key, value in SETTING_DEFAULTS.items():
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

    for key, name, description, content, variables, model_role in PHASE_TWO_PROMPTS:
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

    existing_names = set(
        (
            await session.scalars(
                select(OpenSourceReference.name).where(
                    OpenSourceReference.name.in_(
                        [item[0] for item in OPEN_SOURCE_REFERENCES]
                    )
                )
            )
        ).all()
    )
    for name, license_name, source_url, usage_note in OPEN_SOURCE_REFERENCES:
        if name not in existing_names:
            session.add(
                OpenSourceReference(
                    name=name,
                    license_name=license_name,
                    source_url=source_url,
                    usage_note=usage_note,
                )
            )
    await session.commit()
