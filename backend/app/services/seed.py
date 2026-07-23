from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.services.claim_extractor import DEFAULT_SYSTEM_PROMPT
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

