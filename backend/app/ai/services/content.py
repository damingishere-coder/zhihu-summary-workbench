from __future__ import annotations

import json
from typing import Any

from backend.app.ai.providers.base import StructuredOutputProvider, StructuredProviderResult
from backend.app.schemas.analysis import (
    AnswerClaimBatch,
    AnswerQualityBatch,
    ArticleGeneration,
    ArticleQualityReview,
    ClusterRefinement,
    OpinionMapData,
)
from backend.app.schemas.draft import DraftRewriteResult


QUALITY_SYSTEM_PROMPT = """你是回答质量筛选器。请批量判断每条回答与问题的相关性、
内容质量和信息密度。不得因为立场不同而排除回答；短、广告、重复或明显无关内容应排除。
必须为每个输入 answer_id 返回且只返回一条结果。"""

CLAIM_SYSTEM_PROMPT = """你是回答观点提取器。只基于输入回答提取观点，不补充外部事实。
区分观点、理由、例子、证据、适用条件和风险；不得把个人经历改写为普遍事实。
每条结果必须保留原 answer_id。"""

CLUSTER_SYSTEM_PROMPT = """你是观点聚类修正器。根据粗聚类中的观点和来源，合并真正相似的簇，
识别共识、分歧、适用条件和有价值少数派。不得创造输入中不存在的观点。
source_cluster_indexes 必须引用输入粗聚类索引。"""

OPINION_MAP_SYSTEM_PROMPT = """你是观点地图编辑。请把观点簇整理为直接回答问题的结构，
清楚区分共识、分歧、少数派、条件、误解、风险和建议。source_answer_ids 只能使用输入来源。
write_policy=force 的观点必须写入，write_policy=exclude 的观点不得写入，并遵循 sort_order。"""

ARTICLE_SYSTEM_PROMPT = """你是知乎总结文章编辑。只基于观点地图和来源写作，不捏造数据，
不虚构亲身经历，不按答主逐条复述，不复制独特句式。必须直接回答、说明共识与分歧及其前提，
并返回每个段落对应的 cluster_ids 和 source_answer_ids。write_policy=force 的观点必须写入，
write_policy=exclude 的观点不得写入。文章末尾说明由 AI 辅助整理且需人工审核。"""

REVIEW_SYSTEM_PROMPT = """你是独立文章质量审核器，不参与文章生成。检查共识、分歧、重要观点、
单一来源依赖、近似复制、无来源观点、经历事实化、矛盾数据、高风险领域、模板化、重复和绝对表达。
任何医疗、法律、金融或投资主题都必须标为 high risk 并要求人工审核。"""

REWRITE_SYSTEM_PROMPT = """你是知乎总结草稿的局部编辑器。只重写用户提供的原文，不补充外部事实，
不改变数字、来源含义和风险边界，不虚构经历。根据 instruction 改善表达并只返回重写后的正文。"""


class AnswerQualityService:
    def __init__(self, provider: StructuredOutputProvider):
        self.provider = provider

    async def evaluate_batch(
        self, *, question_title: str, answers: list[dict[str, Any]]
    ) -> StructuredProviderResult[AnswerQualityBatch]:
        return await self.provider.generate_structured(
            system_prompt=QUALITY_SYSTEM_PROMPT,
            user_prompt="输入 JSON：\n"
            + json.dumps(
                {"question_title": question_title, "answers": answers},
                ensure_ascii=False,
            ),
            output_schema=AnswerQualityBatch,
            model_role="fast_text_model",
        )


class AnswerClaimBatchService:
    def __init__(self, provider: StructuredOutputProvider):
        self.provider = provider

    async def extract_batch(
        self, *, question_title: str, answers: list[dict[str, Any]]
    ) -> StructuredProviderResult[AnswerClaimBatch]:
        return await self.provider.generate_structured(
            system_prompt=CLAIM_SYSTEM_PROMPT,
            user_prompt="输入 JSON：\n"
            + json.dumps(
                {"question_title": question_title, "answers": answers},
                ensure_ascii=False,
            ),
            output_schema=AnswerClaimBatch,
            model_role="fast_text_model",
        )


class ClusterRefinementService:
    def __init__(self, provider: StructuredOutputProvider):
        self.provider = provider

    async def refine(
        self, *, question_title: str, rough_clusters: list[dict[str, Any]]
    ) -> StructuredProviderResult[ClusterRefinement]:
        return await self.provider.generate_structured(
            system_prompt=CLUSTER_SYSTEM_PROMPT,
            user_prompt="输入 JSON：\n"
            + json.dumps(
                {
                    "question_title": question_title,
                    "rough_clusters": rough_clusters,
                },
                ensure_ascii=False,
            ),
            output_schema=ClusterRefinement,
            model_role="reasoning_model",
        )


class OpinionMapGenerationService:
    def __init__(self, provider: StructuredOutputProvider):
        self.provider = provider

    async def generate(
        self, *, question_title: str, clusters: list[dict[str, Any]]
    ) -> StructuredProviderResult[OpinionMapData]:
        return await self.provider.generate_structured(
            system_prompt=OPINION_MAP_SYSTEM_PROMPT,
            user_prompt="输入 JSON：\n"
            + json.dumps(
                {"question_title": question_title, "clusters": clusters},
                ensure_ascii=False,
            ),
            output_schema=OpinionMapData,
            model_role="reasoning_model",
        )


class ArticleGenerationService:
    def __init__(self, provider: StructuredOutputProvider):
        self.provider = provider

    async def generate(
        self,
        *,
        question_title: str,
        opinion_map: dict[str, Any],
        clusters: list[dict[str, Any]],
        target_length: int,
    ) -> StructuredProviderResult[ArticleGeneration]:
        return await self.provider.generate_structured(
            system_prompt=ARTICLE_SYSTEM_PROMPT,
            user_prompt="输入 JSON：\n"
            + json.dumps(
                {
                    "question_title": question_title,
                    "opinion_map": opinion_map,
                    "clusters": clusters,
                    "target_length": target_length,
                },
                ensure_ascii=False,
            ),
            output_schema=ArticleGeneration,
            model_role="reasoning_model",
        )


class ArticleReviewService:
    def __init__(self, provider: StructuredOutputProvider):
        self.provider = provider

    async def review(
        self,
        *,
        question_title: str,
        article: dict[str, Any],
        opinion_map: dict[str, Any],
    ) -> StructuredProviderResult[ArticleQualityReview]:
        return await self.provider.generate_structured(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_prompt="输入 JSON：\n"
            + json.dumps(
                {
                    "question_title": question_title,
                    "article": article,
                    "opinion_map": opinion_map,
                },
                ensure_ascii=False,
            ),
            output_schema=ArticleQualityReview,
            model_role="reasoning_model",
        )


class DraftRewriteService:
    def __init__(self, provider: StructuredOutputProvider):
        self.provider = provider

    async def rewrite(
        self,
        *,
        question_title: str,
        scope: str,
        text: str,
        instruction: str,
    ) -> StructuredProviderResult[DraftRewriteResult]:
        return await self.provider.generate_structured(
            system_prompt=REWRITE_SYSTEM_PROMPT,
            user_prompt="输入 JSON：\n"
            + json.dumps(
                {
                    "question_title": question_title,
                    "scope": scope,
                    "text": text,
                    "instruction": instruction
                    or "在不改变原意和事实边界的前提下，使表达更清楚、紧凑。",
                },
                ensure_ascii=False,
            ),
            output_schema=DraftRewriteResult,
            model_role="fast_text_model",
        )
