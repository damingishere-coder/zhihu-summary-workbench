from __future__ import annotations

import hashlib
import json
import math
import struct
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers.base import ProviderUsage
from backend.app.ai.providers.cached import CachedStructuredProvider
from backend.app.ai.providers.factory import create_structured_provider
from backend.app.ai.providers.local_embedding import LocalEmbeddingProvider
from backend.app.ai.services.content import (
    ARTICLE_SYSTEM_PROMPT,
    CLAIM_SYSTEM_PROMPT,
    CLUSTER_SYSTEM_PROMPT,
    OPINION_MAP_SYSTEM_PROMPT,
    QUALITY_SYSTEM_PROMPT,
    SURVEY_QUALITY_INSTRUCTION,
    REVIEW_SYSTEM_PROMPT,
    REWRITE_SYSTEM_PROMPT,
    AnswerClaimBatchService,
    AnswerQualityService,
    ArticleGenerationService,
    ArticleReviewService,
    ClusterRefinementService,
    DraftRewriteService,
    OpinionMapGenerationService,
)
from backend.app.collectors.zhihu import ZhihuCollector, ZhihuFetchResult, basic_filter_reason
from backend.app.core.config import Settings
from backend.app.models.common import utc_now
from backend.app.models.content import (
    Answer,
    AnswerAnalysis,
    AnswerVersion,
    ArticleParagraphSource,
    Claim,
    ClaimCluster,
    ClaimEmbedding,
    ClusterAnswerLink,
    OpinionMap,
)
from backend.app.models.core import (
    ArticleDraft,
    ArticleVersion,
    ModelUsageLog,
    Question,
    QuestionSource,
    TaskJob,
)
from backend.app.schemas.analysis import (
    ArticleGeneration,
    ArticleQualityReview,
    FetchAnswersRequest,
)
from backend.app.services.settings import configured_settings_copy, provider_mode
from backend.app.services.prompts import get_active_prompt
from backend.app.services.analysis_batches import persist_analysis_batch


async def record_model_usage(
    session: AsyncSession,
    usage: ProviderUsage,
    *,
    question_id: str,
    task_id: str | None,
    stage: str | None = None,
) -> None:
    session.add(
        ModelUsageLog(
            question_id=question_id,
            task_id=task_id,
            provider=usage.provider,
            model_role=usage.model_role,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost=Decimal(str(usage.estimated_cost)),
            duration_ms=usage.duration_ms,
            status="success",
            stage=stage or usage.model_role,
            cache_hit=usage.cache_hit,
            fallback_used=usage.fallback_used,
            retry_count=usage.retry_count,
        )
    )


async def fetch_and_store_answers(
    session: AsyncSession,
    question: Question,
    settings: Settings,
    request: FetchAnswersRequest,
    *,
    collector: ZhihuCollector | None = None,
    precollected: ZhihuFetchResult | None = None,
) -> tuple[ZhihuFetchResult, dict[str, int]]:
    if not question.external_id:
        raise ValueError("问题缺少知乎 question id，无法采集回答")
    if precollected is None:
        runtime = await configured_settings_copy(session, settings)
        active_collector = collector or ZhihuCollector(runtime)
        result = await active_collector.fetch_question_and_answers(
            question.external_id,
            max_answers=request.max_answers,
            mode=request.mode,
            collector_mode=request.collector_mode,
        )
    else:
        result = precollected
    if result.question:
        incoming = result.question
        question.title = incoming.title or question.title
        question.url = incoming.url or question.url
        question.description = incoming.description or question.description
        question.hot_rank = incoming.hot_rank
        question.hot_score = incoming.hot_score
        question.answer_count = incoming.answer_count
        question.follower_count = incoming.follower_count
        question.fetched_at = utc_now()
        question.content_hash = hashlib.sha256(
            f"{question.title}|{question.url}|{question.description}".encode("utf-8")
        ).hexdigest()
        session.add(
            QuestionSource(
                question_id=question.id,
                source_type=f"zhihu_{result.collector_mode}",
                source_url=question.url,
                raw_data={
                    "batch_id": result.batch_id,
                    "fetched_at": utc_now().isoformat(),
                    "snapshot": incoming.raw_snapshot,
                },
            )
        )

    existing_answers = (
        await session.scalars(
            select(Answer).where(Answer.question_id == question.id)
        )
    ).all()
    existing_by_external = {
        item.answer_external_id: item for item in existing_answers
    }
    created = 0
    updated = 0
    for incoming in result.answers:
        answer = existing_by_external.get(incoming.external_id)
        # Identical text from different answers still represents different authors.
        filter_reason = basic_filter_reason(incoming.plain_content)
        values = {
            "author_name": incoming.author_name,
            "author_url": incoming.author_url,
            "answer_url": incoming.answer_url,
            "html_content": incoming.html_content,
            "markdown_content": incoming.markdown_content,
            "plain_content": incoming.plain_content,
            "content_hash": incoming.content_hash,
            "vote_count": incoming.vote_count,
            "comment_count": incoming.comment_count,
            "published_at": incoming.published_at,
            "external_updated_at": incoming.updated_at,
            "sort_order": incoming.sort_order,
            "media_json": incoming.media,
            "fetch_batch": result.batch_id,
            "included_for_analysis": not bool(filter_reason),
            "filter_reason": filter_reason,
            "raw_snapshot": incoming.raw_snapshot,
        }
        content_changed = answer is None or answer.content_hash != incoming.content_hash
        if answer is None:
            answer = Answer(
                question_id=question.id,
                answer_external_id=incoming.external_id,
                **values,
            )
            session.add(answer)
            await session.flush()
            created += 1
            version = 1
        else:
            for key, value in values.items():
                setattr(answer, key, value)
            updated += 1
            version = int(
                (
                    await session.scalar(
                        select(func.max(AnswerVersion.version)).where(
                            AnswerVersion.answer_id == answer.id
                        )
                    )
                )
                or 0
            ) + 1
        if content_changed:
            session.add(
                AnswerVersion(
                    answer_id=answer.id,
                    version=version,
                    content_hash=incoming.content_hash,
                    plain_content=incoming.plain_content,
                    raw_snapshot=incoming.raw_snapshot,
                )
            )

    question.status = "cleaning_answers"
    await session.commit()
    included = int(
        (
            await session.scalar(
                select(func.count(Answer.id)).where(
                    Answer.question_id == question.id,
                    Answer.included_for_analysis.is_(True),
                )
            )
        )
        or 0
    )
    total = int(
        (
            await session.scalar(
                select(func.count(Answer.id)).where(Answer.question_id == question.id)
            )
        )
        or 0
    )
    return result, {
        "fetched": len(result.answers),
        "created": created,
        "updated": updated,
        "included": included,
        "filtered": total - included,
    }


async def _runtime_provider(
    session: AsyncSession, settings: Settings
):
    runtime = await configured_settings_copy(session, settings)
    mode = await provider_mode(session, settings)
    provider = create_structured_provider(mode, runtime)
    fingerprint = ":".join(
        (
            mode,
            runtime.codex_model,
            runtime.codex_path,
            runtime.deepseek_fast_model,
            runtime.deepseek_reasoning_model,
            runtime.deepseek_fallback_model,
        )
    )
    return (
        CachedStructuredProvider(
            provider,
            session,
            fingerprint=fingerprint,
            cache_enabled=runtime.response_cache_enabled,
            daily_budget=runtime.daily_model_budget,
            pause_on_budget_exceeded=runtime.pause_on_budget_exceeded,
        ),
        mode,
    )


async def evaluate_answers(
    session: AsyncSession,
    question: Question,
    settings: Settings,
    *,
    task: TaskJob | None = None,
) -> dict[str, int]:
    provider, _ = await _runtime_provider(session, settings)
    service = AnswerQualityService(
        provider,
        await get_active_prompt(
            session, "answer_quality_evaluation", QUALITY_SYSTEM_PROMPT
        ) + "\n" + SURVEY_QUALITY_INSTRUCTION,
    )
    answers = (
        await session.scalars(
            select(Answer)
            .where(Answer.question_id == question.id)
            .order_by(Answer.sort_order)
        )
    ).all()
    # Re-evaluate previous automatic exclusions under the survey criteria, while
    # retaining explicit manual exclusions. Old quality reasons are not permanent.
    for item in answers:
        if item.filter_reason != "运营人员手动排除":
            item.filter_reason = basic_filter_reason(item.plain_content)
    candidates = [item for item in answers if not item.filter_reason]
    batch_size = max(1, settings.answer_quality_batch_size)
    returned_ids: set[str] = set()
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        result = await service.evaluate_batch(
            question_title=question.title,
            answers=[
                {
                    "answer_id": item.id,
                    "plain_content": item.plain_content,
                    "vote_count": item.vote_count,
                    "comment_count": item.comment_count,
                    "filter_reason": item.filter_reason,
                }
                for item in batch
            ],
        )
        await record_model_usage(
            session,
            result.usage,
            question_id=question.id,
            task_id=task.id if task else None,
            stage="evaluating_answers",
        )
        by_id = {item.id: item for item in batch}
        for quality in result.data.items:
            answer = by_id.get(quality.answer_id)
            if not answer:
                continue
            returned_ids.add(answer.id)
            answer.included_for_analysis = quality.include
            answer.filter_reason = "" if quality.include else quality.reason
            analysis = await session.scalar(
                select(AnswerAnalysis).where(AnswerAnalysis.answer_id == answer.id)
            )
            if not analysis:
                analysis = AnswerAnalysis(answer_id=answer.id)
                session.add(analysis)
            analysis.quality_score = quality.quality_score
            analysis.relevance_score = quality.relevance_score
            analysis.information_density = quality.information_density
            analysis.include = quality.include
            analysis.reason = quality.reason
        await persist_analysis_batch(session, task=task, stage="evaluating_answers",
            completed=offset + len(batch), total=len(candidates), start_progress=30, end_progress=40)
    for answer in answers:
        if answer.filter_reason and answer.id not in returned_ids:
            answer.included_for_analysis = False
            analysis = await session.scalar(
                select(AnswerAnalysis).where(AnswerAnalysis.answer_id == answer.id)
            )
            if not analysis:
                analysis = AnswerAnalysis(answer_id=answer.id)
                session.add(analysis)
            analysis.include = False
            analysis.reason = answer.filter_reason
    question.status = "evaluating_answers"
    await session.commit()
    return {
        "total": len(answers),
        "included": sum(item.included_for_analysis for item in answers),
        "filtered": sum(not item.included_for_analysis for item in answers),
    }


async def extract_claims(
    session: AsyncSession,
    question: Question,
    settings: Settings,
    *,
    task: TaskJob | None = None,
) -> dict[str, int]:
    provider, _ = await _runtime_provider(session, settings)
    service = AnswerClaimBatchService(
        provider,
        await get_active_prompt(
            session, "answer_claim_batch_extraction", CLAIM_SYSTEM_PROMPT
        ),
    )
    answers = (
        await session.scalars(
            select(Answer)
            .where(
                Answer.question_id == question.id,
                Answer.included_for_analysis.is_(True),
            )
            .order_by(Answer.sort_order)
        )
    ).all()
    existing_claims = (
        await session.scalars(
            select(Claim).where(Claim.question_id == question.id)
        )
    ).all()
    reusable = {
        (item.answer_id, item.content_hash): item for item in existing_claims
    }
    kept_ids: set[str] = set()
    segments: dict[str, list[dict]] = defaultdict(list)
    batch_size = max(1, settings.claim_extraction_batch_size)
    for offset in range(0, len(answers), batch_size):
        batch = answers[offset : offset + batch_size]
        result = await service.extract_batch(
            question_title=question.title,
            answers=[
                {
                    "answer_id": item.id,
                    "plain_content": item.plain_content,
                }
                for item in batch
            ],
        )
        await record_model_usage(
            session,
            result.usage,
            question_id=question.id,
            task_id=task.id if task else None,
            stage="extracting_claims",
        )
        by_id = {item.id: item for item in batch}
        for extracted in result.data.items:
            answer = by_id.get(extracted.answer_id)
            if not answer:
                continue
            analysis = await session.scalar(
                select(AnswerAnalysis).where(AnswerAnalysis.answer_id == answer.id)
            )
            if not analysis:
                analysis = AnswerAnalysis(answer_id=answer.id)
                session.add(analysis)
            segments[answer.id].append(extracted.model_dump())
            analysis.summary = "\n".join(item["summary"] for item in segments[answer.id])
            analysis.structured_result = {**extracted.model_dump(), "segments": segments[answer.id]}
            analysis.quality_score = extracted.quality_score
            analysis.relevance_score = extracted.relevance_score
            for index, content in enumerate(extracted.core_claims):
                normalized = content.strip()
                if not normalized:
                    continue
                content_hash = hashlib.sha256(
                    normalized.encode("utf-8")
                ).hexdigest()
                claim = reusable.get((answer.id, content_hash))
                metadata = {
                    "claim_index": index,
                    "source_start": extracted.source_start,
                    "source_end": extracted.source_end or len(answer.plain_content),
                    "source_hash": answer.content_hash,
                    "position": extracted.position,
                    "applicable_conditions": extracted.applicable_conditions,
                    "risks_or_limitations": extracted.risks_or_limitations,
                }
                if claim:
                    claim.content = normalized
                    claim.metadata_json = metadata
                else:
                    claim = Claim(
                        answer_id=answer.id,
                        question_id=question.id,
                        content=normalized,
                        content_hash=content_hash,
                        metadata_json=metadata,
                    )
                    session.add(claim)
                    await session.flush()
                    reusable[(answer.id, content_hash)] = claim
                kept_ids.add(claim.id)
        await persist_analysis_batch(session, task=task, stage="extracting_claims",
            completed=offset + len(batch), total=len(answers), start_progress=42, end_progress=54)
    for claim in existing_claims:
        if claim.id not in kept_ids:
            await session.delete(claim)
    question.status = "extracting_claims"
    await session.commit()
    return {
        "answers": len(answers),
        "claims": int(
            (
                await session.scalar(
                    select(func.count(Claim.id)).where(
                        Claim.question_id == question.id
                    )
                )
            )
            or 0
        ),
    }


def _pack_vector(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack_vector(payload: bytes, dimensions: int) -> list[float]:
    return list(struct.unpack(f"<{dimensions}f", payload))


async def generate_embeddings(
    session: AsyncSession,
    question: Question,
    settings: Settings,
) -> dict[str, int]:
    provider = LocalEmbeddingProvider()
    claims = (
        await session.scalars(
            select(Claim).where(Claim.question_id == question.id).order_by(Claim.id)
        )
    ).all()
    created = 0
    cached = 0
    for claim in claims:
        existing = await session.scalar(
            select(ClaimEmbedding).where(ClaimEmbedding.claim_id == claim.id)
        )
        if (
            existing
            and existing.content_hash == claim.content_hash
            and existing.model == provider.model
        ):
            cached += 1
            continue
        vector = (await provider.embed([claim.content]))[0]
        if existing:
            existing.provider = "local"
            existing.model = provider.model
            existing.dimensions = provider.dimensions
            existing.vector = _pack_vector(vector)
            existing.content_hash = claim.content_hash
        else:
            session.add(
                ClaimEmbedding(
                    claim_id=claim.id,
                    provider="local",
                    model=provider.model,
                    dimensions=provider.dimensions,
                    vector=_pack_vector(vector),
                    content_hash=claim.content_hash,
                )
            )
        created += 1
    question.status = "generating_embeddings"
    await session.commit()
    return {"claims": len(claims), "computed": created, "cached": cached}


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _rough_cluster(
    rows: list[tuple[Claim, list[float]]], threshold: float
) -> list[list[tuple[Claim, list[float]]]]:
    clusters: list[list[tuple[Claim, list[float]]]] = []
    centroids: list[list[float]] = []
    for row in rows:
        claim, vector = row
        if not clusters:
            clusters.append([row])
            centroids.append(vector[:])
            continue
        scores = [_cosine(vector, centroid) for centroid in centroids]
        best = max(range(len(scores)), key=scores.__getitem__)
        if scores[best] < threshold:
            clusters.append([row])
            centroids.append(vector[:])
            continue
        clusters[best].append(row)
        size = len(clusters[best])
        centroid = [
            ((size - 1) * old + value) / size
            for old, value in zip(centroids[best], vector, strict=False)
        ]
        norm = math.sqrt(sum(value * value for value in centroid)) or 1.0
        centroids[best] = [value / norm for value in centroid]
    return clusters


async def refine_clusters(
    session: AsyncSession,
    question: Question,
    settings: Settings,
    *,
    task: TaskJob | None = None,
) -> dict[str, int]:
    provider, _ = await _runtime_provider(session, settings)
    service = ClusterRefinementService(
        provider,
        await get_active_prompt(
            session, "claim_cluster_refinement", CLUSTER_SYSTEM_PROMPT
        ),
    )
    claims = (
        await session.scalars(
            select(Claim).where(Claim.question_id == question.id).order_by(Claim.id)
        )
    ).all()
    rows: list[tuple[Claim, list[float]]] = []
    for claim in claims:
        embedding = await session.scalar(
            select(ClaimEmbedding).where(ClaimEmbedding.claim_id == claim.id)
        )
        if embedding:
            rows.append(
                (claim, _unpack_vector(embedding.vector, embedding.dimensions))
            )
    if not rows:
        raise ValueError("没有可聚类的观点向量")
    # One claim per input unit: a semantic model can separate contradictory claims.
    # Character similarity must never force claims from opposite sides into one unit.
    rough = [[row] for row in rows]
    rough_payload = [
        {
            "index": index,
            "claim_ids": [claim.id for claim, _ in members],
            "claims": [claim.content for claim, _ in members],
            "answer_ids": list(
                dict.fromkeys(claim.answer_id for claim, _ in members)
            ),
        }
        for index, members in enumerate(rough)
    ]
    service.system_prompt += "\n输入每项为独立观点，可以合并或保持独立。每个索引必须且只能分配一次，不得漏掉少数派。source_relations 数组必须对每个 source_cluster_index 标明其相对本簇中心结论的 relation：supports/opposes/conditional/related；来源数不是支持票数。"
    service.system_prompt += "\n当前用途是向普通读者展示几类主要观点各有多少作者。按语义相近的观点方向归组，而非逐句生成小标题：措辞不同、不同例子、不同时间或人群条件可以属于同一观点方向，用 conditional/related 区分，保留少数派与反对者。通常将一批观点归为 8-12 个可比较方向（内容很少时可以更少，确有必要时可更多），不要把几十条输入原样拆成几十个单条簇。标题写清共同核心判断，summary 说明共同核心和各来源的条件差异，不能让每人看起来都支持同组全部细节；source_relations 相对于标题的核心判断。相同作者的补充理由尽量放在所属方向中，不单独作为统计大类。"
    service.system_prompt += "\n每个统计方向只包含一个可独立认同或反对的核心判断。可独立成立的乐观判断和风险判断分别设类，例如‘出海提供增长空间’和‘海外扩张受到约束’，不能用‘但/同时/以及’拼为复合命题后统一统计支持人数。"
    refined_items = []
    for start in range(0, len(rough_payload), 64):
        batch = rough_payload[start:start + 64]
        result = await service.refine(question_title=question.title, rough_clusters=batch)
        indexes = [index for item in result.data.clusters for index in item.source_cluster_indexes]
        expected = {item["index"] for item in batch}
        if set(indexes) != expected or len(indexes) != len(expected):
            raise ValueError("聚类结果遗漏、重复或引用未知观点，已停止以保留来源")
        refined_items.extend(result.data.clusters)
        await record_model_usage(session, result.usage, question_id=question.id,
                                 task_id=task.id if task else None, stage="refining_clusters")
        await persist_analysis_batch(session, task=task, stage="refining_clusters",
            completed=start + len(batch), total=len(rough_payload), start_progress=70, end_progress=74,
            unit="条观点")
    if len(rough_payload) > 64:
        from backend.app.services.cluster_batches import GLOBAL_MERGE_INSTRUCTION, flatten_cluster_groups
        global_service = ClusterRefinementService(provider, service.system_prompt + "\n" + GLOBAL_MERGE_INSTRUCTION)
        merged = await global_service.refine(question_title=question.title, rough_clusters=[
            {"index": i, "claims": [item.name, item.summary], "claim_ids": [], "answer_ids": []}
            for i, item in enumerate(refined_items)
        ])
        initial_count = len(refined_items)
        refined_items = flatten_cluster_groups(refined_items, merged.data.clusters, set(range(len(rough_payload))))
        await record_model_usage(session, merged.usage, question_id=question.id,
                                 task_id=task.id if task else None, stage="merging_cluster_batches")
        await persist_analysis_batch(session, task=task, stage="merging_cluster_batches",
            completed=initial_count, total=initial_count, start_progress=74, end_progress=76, unit="个方向")
    old_clusters = (
        await session.scalars(
            select(ClaimCluster).where(ClaimCluster.question_id == question.id)
        )
    ).all()
    if old_clusters:
        old_ids = [item.id for item in old_clusters]
        await session.execute(
            delete(ClusterAnswerLink).where(
                ClusterAnswerLink.cluster_id.in_(old_ids)
            )
        )
        await session.execute(
            delete(ClaimCluster).where(ClaimCluster.id.in_(old_ids))
        )
    created = 0
    for refined in refined_items:
        selected = [
            rough_payload[index]
            for index in refined.source_cluster_indexes
            if 0 <= index < len(rough_payload)
        ]
        if not selected:
            continue
        claim_ids = list(
            dict.fromkeys(
                claim_id for item in selected for claim_id in item["claim_ids"]
            )
        )
        answer_ids = list(
            dict.fromkeys(
                answer_id for item in selected for answer_id in item["answer_ids"]
            )
        )
        relations: dict[str, set[str]] = defaultdict(set)
        relation_map = {row.source_cluster_index: row.relation for row in refined.source_relations}
        for item in selected:
            relation = relation_map.get(item["index"], "related")
            for answer_id in item["answer_ids"]:
                relations[answer_id].add(relation)
        from backend.app.services.opinion_survey import combined_relation
        answer_relations = {key: combined_relation(value) for key, value in relations.items()}
        cluster = ClaimCluster(
            question_id=question.id,
            name=refined.name,
            summary=refined.summary,
            cluster_type=refined.cluster_type,
            confidence=refined.confidence,
            support_count=sum(value == "supports" for value in answer_relations.values()),
            opposing_reasons=refined.opposing_reasons,
            applicable_conditions=refined.applicable_conditions,
            is_mainstream=refined.is_mainstream,
            is_minority=refined.is_minority,
            is_controversial=refined.is_controversial,
            information_gain=refined.information_gain,
            metadata_json={
                "claim_ids": claim_ids,
                "sort_order": created,
                "write_policy": "auto",
                "source_count": len(answer_ids),
                "opposition_count": sum(value == "opposes" for value in answer_relations.values()),
            },
        )
        session.add(cluster)
        await session.flush()
        for answer_id in answer_ids:
            session.add(
                ClusterAnswerLink(
                    cluster_id=cluster.id,
                    answer_id=answer_id,
                    relation=answer_relations[answer_id],
                )
            )
        for claim in claims:
            if claim.id in claim_ids:
                claim.metadata_json = {
                    **(claim.metadata_json or {}),
                    "cluster_id": cluster.id,
                }
        created += 1
    if not created:
        raise ValueError("聚类修正没有返回有效观点簇")
    question.status = "refining_clusters"
    await session.commit()
    return {"rough_clusters": len(rough), "clusters": created}


async def cluster_rows(
    session: AsyncSession, question_id: str
) -> list[dict[str, Any]]:
    clusters = (
        await session.scalars(
            select(ClaimCluster)
            .where(ClaimCluster.question_id == question_id)
            .order_by(
                ClaimCluster.is_mainstream.desc(),
                ClaimCluster.support_count.desc(),
                ClaimCluster.created_at,
            )
        )
    ).all()
    result: list[dict[str, Any]] = []
    for cluster in clusters:
        links = list((await session.scalars(select(ClusterAnswerLink).where(ClusterAnswerLink.cluster_id == cluster.id))).all())
        source_relations = {link.answer_id: link.relation for link in links}
        answer_ids = (
            await session.scalars(
                select(ClusterAnswerLink.answer_id).where(
                    ClusterAnswerLink.cluster_id == cluster.id
                )
            )
        ).all()
        answers = (
            (
                await session.scalars(
                    select(Answer).where(Answer.id.in_(answer_ids))
                )
            ).all()
            if answer_ids
            else []
        )
        answer_lookup = {answer.id: answer for answer in answers}
        metadata = cluster.metadata_json or {}
        write_policy = str(metadata.get("write_policy") or "auto")
        if write_policy not in {"auto", "force", "exclude"}:
            write_policy = "auto"
        result.append(
            {
                "id": cluster.id,
                "question_id": cluster.question_id,
                "name": cluster.name,
                "summary": cluster.summary,
                "cluster_type": cluster.cluster_type,
                "confidence": cluster.confidence,
                "support_count": cluster.support_count,
                "source_count": len(source_relations),
                "opposition_count": sum(value == "opposes" for value in source_relations.values()),
                "source_relations": source_relations,
                "source_evidence_quotes": metadata.get("source_evidence_quotes", {}),
                "stance_matrix_answers": metadata.get("stance_matrix_answers", 0),
                "opposing_reasons": cluster.opposing_reasons or [],
                "applicable_conditions": cluster.applicable_conditions or [],
                "is_mainstream": cluster.is_mainstream,
                "is_minority": cluster.is_minority,
                "is_controversial": cluster.is_controversial,
                "information_gain": cluster.information_gain,
                "sort_order": int(metadata.get("sort_order") or 0),
                "write_policy": write_policy,
                "source_answer_ids": list(dict.fromkeys(answer_ids)),
                "claim_ids": metadata.get("claim_ids", []),
                "sources": [
                    {
                        "answer_id": answer_id,
                        "author_name": answer_lookup[answer_id].author_name,
                        "answer_url": answer_lookup[answer_id].answer_url,
                        "excerpt": answer_lookup[answer_id].plain_content[:220],
                    }
                    for answer_id in answer_ids
                    if answer_id in answer_lookup
                ],
            }
        )
    return sorted(
        result,
        key=lambda item: (
            item["sort_order"],
            0 if item["is_mainstream"] else 1,
            -item["support_count"],
            item["id"],
        ),
    )


async def reanalyze_cluster(
    session: AsyncSession,
    cluster: ClaimCluster,
    settings: Settings,
) -> ClaimCluster:
    claim_ids = list((cluster.metadata_json or {}).get("claim_ids", []))
    claims = list(
        (
            await session.scalars(
                select(Claim).where(Claim.id.in_(claim_ids))
            )
        ).all()
    )
    if not claims:
        raise ValueError("观点簇没有可重新分析的观点")
    question = await session.get(Question, cluster.question_id)
    if not question:
        raise ValueError("观点簇所属问题不存在")
    provider, _ = await _runtime_provider(session, settings)
    result = await ClusterRefinementService(
        provider,
        await get_active_prompt(
            session, "claim_cluster_refinement", CLUSTER_SYSTEM_PROMPT
        ),
    ).refine(
        question_title=question.title,
        rough_clusters=[
            {
                "index": 0,
                "claim_ids": claim_ids,
                "claims": [claim.content for claim in claims],
                "answer_ids": list(
                    dict.fromkeys(claim.answer_id for claim in claims)
                ),
            }
        ],
    )
    await record_model_usage(
        session,
        result.usage,
        question_id=question.id,
        task_id=None,
        stage="refining_clusters",
    )
    if not result.data.clusters:
        raise ValueError("局部重新分析没有返回观点簇")
    refined = result.data.clusters[0]
    cluster.name = refined.name
    cluster.summary = refined.summary
    cluster.cluster_type = refined.cluster_type
    cluster.confidence = refined.confidence
    cluster.opposing_reasons = refined.opposing_reasons
    cluster.applicable_conditions = refined.applicable_conditions
    cluster.is_mainstream = refined.is_mainstream
    cluster.is_minority = refined.is_minority
    cluster.is_controversial = refined.is_controversial
    cluster.information_gain = refined.information_gain
    await session.commit()
    await session.refresh(cluster)
    return cluster


async def generate_opinion_map(
    session: AsyncSession,
    question: Question,
    settings: Settings,
    *,
    task: TaskJob | None = None,
) -> OpinionMap:
    from backend.app.services.survey_stances import ensure_survey_stances
    await ensure_survey_stances(session, question, settings, task=task)
    provider, _ = await _runtime_provider(session, settings)
    clusters = [
        item
        for item in await cluster_rows(session, question.id)
        if item["write_policy"] != "exclude"
    ]
    if not clusters:
        raise ValueError("没有观点簇，无法生成观点地图")
    clusters.sort(
        key=lambda item: (
            0 if item["write_policy"] == "force" else 1,
            item["sort_order"],
        )
    )
    result = await OpinionMapGenerationService(
        provider,
        await get_active_prompt(
            session, "opinion_map_generation", OPINION_MAP_SYSTEM_PROMPT
        ),
    ).generate(
        question_title=question.title, clusters=clusters
    )
    await record_model_usage(
        session,
        result.usage,
        question_id=question.id,
        task_id=task.id if task else None,
        stage="generating_opinion_map",
    )
    version = int(
        (
            await session.scalar(
                select(func.max(OpinionMap.version)).where(
                    OpinionMap.question_id == question.id
                )
            )
        )
        or 0
    ) + 1
    item = OpinionMap(
        question_id=question.id,
        version=version,
        status="generated",
        content_json=result.data.model_dump(),
    )
    session.add(item)
    question.status = "generating_opinion_map"
    await session.commit()
    await session.refresh(item)
    return item


async def generate_article(
    session: AsyncSession,
    question: Question,
    settings: Settings,
    *,
    task: TaskJob | None = None,
    feedback: list[str] | None = None,
) -> tuple[ArticleDraft, ArticleGeneration]:
    if feedback is None and task:
        feedback = task.result.get('survey_review_feedback')
    from backend.app.services.opinion_survey import build_survey, survey_paragraphs, SURVEY_INSTRUCTION
    from backend.app.services.survey_stances import ensure_survey_stances
    await ensure_survey_stances(session, question, settings, task=task)
    opinion = await session.scalar(
        select(OpinionMap)
        .where(OpinionMap.question_id == question.id)
        .order_by(OpinionMap.version.desc())
        .limit(1)
    )
    if not opinion:
        raise ValueError("没有观点地图，无法生成文章")
    clusters = [
        item
        for item in await cluster_rows(session, question.id)
        if item["write_policy"] != "exclude"
    ]
    clusters.sort(
        key=lambda item: (
            0 if item["write_policy"] == "force" else 1,
            item["sort_order"],
        )
    )
    snapshot_answers = list((await session.scalars(select(Answer).where(Answer.question_id == question.id))).all())
    survey = build_survey([
        {"id": a.id, "author_url": a.author_url, "author_name": a.author_name,
         "answer_url": a.answer_url, "included_for_analysis": a.included_for_analysis}
        for a in snapshot_answers
    ], clusters)
    request_hash = hashlib.sha256(json.dumps({"opinion": opinion.content_json, "clusters": clusters, "survey": survey,
        "source_hashes": {a.id: a.content_hash for a in snapshot_answers},
        "feedback": feedback, "input_hash": task.result.get("checkpoints", {}).get("fetch", {}).get("input_hash") if task else None},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if task:
        existing = await session.scalar(select(ArticleVersion).where(ArticleVersion.source_task_id == task.id)
            .order_by(ArticleVersion.created_at.desc()).limit(1))
        if existing and existing.source_snapshot.get("request_hash") == request_hash:
            saved_draft = await session.get(ArticleDraft, existing.draft_id)
            if saved_draft.current_version != existing.version:
                raise ValueError("草稿已有人工修改，请先审核当前版本，不能用旧任务覆盖")
            return saved_draft, ArticleGeneration(title=existing.title, content=existing.content,
                paragraphs=existing.source_snapshot["paragraphs"])
    provider, _ = await _runtime_provider(session, settings)
    result = await ArticleGenerationService(
        provider,
        await get_active_prompt(session, "article_generation", ARTICLE_SYSTEM_PROMPT)
        + "\n以下为当前产品的写作要求，优先于旧模板中的‘直接回答问题’：\n" + SURVEY_INSTRUCTION
        + ("\n修正以下独立审核问题，仍只可使用已有来源：" + json.dumps(feedback, ensure_ascii=False) if feedback else ""),
    ).generate(
        question_title=question.title,
        opinion_map=opinion.content_json,
        clusters=clusters,
        target_length=settings.article_target_length,
        survey=survey,
        source_answers={a.id: {"author_url": a.author_url, "content": a.plain_content} for a in snapshot_answers},
    )
    await record_model_usage(
        session,
        result.usage,
        question_id=question.id,
        task_id=task.id if task else None,
        stage="generating_article",
    )
    statistics = survey_paragraphs(survey, [a.id for a in snapshot_answers])
    result.data.content = "\n\n".join(p.content for p in statistics) + "\n\n" + result.data.content
    result.data.paragraphs = statistics + result.data.paragraphs
    capture = task.result.get("checkpoints", {}).get("fetch", {}).get("metadata", {}).get("capture", {}) if task else {}
    if capture:
        from backend.app.schemas.analysis import ArticleParagraph
        count = capture.get("collected_answer_count", 0)
        coverage = f"采集范围：本次读取并保存 {count} 条可访问回答。"
        if count != len(snapshot_answers):
            coverage += f"本篇统计使用累计保存的 {len(snapshot_answers)} 条回答，包含此前采集资料，已按回答 ID 去重。"
        coverage += "已观察到页面末尾，仍可能存在不可访问或后续新增的回答。" if capture.get("reached_end") else "未确认读取全部回答，以下总结仅代表已采集样本。"
        reason = {"time_budget": "达到采集时间预算", "no_progress": "连续回滑未出现新回答，按本次可获取的最多回答完成采集", "answer_limit": "达到采样数量"}.get(capture.get("stop_reason"))
        if reason:
            coverage += f"停止原因：{reason}。"
        result.data.content += "\n\n> " + coverage
        result.data.paragraphs.append(ArticleParagraph(paragraph_id="capture_scope", kind="disclosure", content=coverage))
    draft = await session.scalar(
        select(ArticleDraft)
        .where(ArticleDraft.question_id == question.id)
        .order_by(ArticleDraft.updated_at.desc())
        .limit(1)
    )
    if draft:
        draft.current_version += 1
        draft.title = result.data.title
        draft.content = result.data.content
        draft.analysis_snapshot = {
            "opinion_map": opinion.content_json,
            "opinion_map_version": opinion.version,
            "answer_count": len(opinion.content_json.get("source_answer_ids", [])),
            "cluster_count": len(clusters),
            "opinion_survey": survey,
        }
        draft.status = "waiting_review"
        draft.review_result = {}
        draft.reviewed_at = None
    else:
        draft = ArticleDraft(
            question_id=question.id,
            status="waiting_review",
            current_version=1,
            title=result.data.title,
            content=result.data.content,
            analysis_snapshot={
                "opinion_map": opinion.content_json,
                "opinion_map_version": opinion.version,
                "answer_count": len(
                    opinion.content_json.get("source_answer_ids", [])
                ),
                "cluster_count": len(clusters),
                "opinion_survey": survey,
            },
            review_result={},
        )
        session.add(draft)
        await session.flush()
    version = ArticleVersion(
        draft_id=draft.id,
        version=draft.current_version,
        title=draft.title,
        content=draft.content,
        source_task_id=task.id if task else None,
    )
    version.source_snapshot = {
        "request_hash": request_hash,
        "opinion_survey": survey,
        "opinion_map": opinion.content_json,
        "answers": {a.id: {"id": a.id, "author": a.author_name, "url": a.answer_url,
                            "author_url": a.author_url, "included_for_analysis": a.included_for_analysis,
                            "content": a.plain_content, "hash": a.content_hash} for a in snapshot_answers},
        "clusters": clusters,
        "paragraphs": [p.model_dump(mode="json") for p in result.data.paragraphs],
        "capture": (task.result.get("checkpoints", {}).get("fetch", {}).get("metadata", {}).get("capture", {}) if task else {}),
    }
    session.add(version)
    await session.flush()
    valid_answer_ids = set(
        (
            await session.scalars(
                select(Answer.id).where(Answer.question_id == question.id)
            )
        ).all()
    )
    valid_cluster_ids = {item["id"] for item in clusters}
    for paragraph in result.data.paragraphs:
        answer_ids = [
            item for item in paragraph.source_answer_ids if item in valid_answer_ids
        ]
        cluster_ids = [
            item for item in paragraph.cluster_ids if item in valid_cluster_ids
        ]
        if not answer_ids and not cluster_ids:
            session.add(
                ArticleParagraphSource(
                    article_version_id=version.id,
                    paragraph_id=paragraph.paragraph_id,
                    answer_id=None,
                    cluster_id=None,
                )
            )
        for answer_id in answer_ids:
            session.add(
                ArticleParagraphSource(
                    article_version_id=version.id,
                    paragraph_id=paragraph.paragraph_id,
                    answer_id=answer_id,
                    cluster_id=None,
                )
            )
        for cluster_id in cluster_ids:
            session.add(
                ArticleParagraphSource(
                    article_version_id=version.id,
                    paragraph_id=paragraph.paragraph_id,
                    answer_id=None,
                    cluster_id=cluster_id,
                )
            )
    question.status = "reviewing_article"
    await session.commit()
    await session.refresh(draft)
    return draft, result.data


async def review_article(
    session: AsyncSession,
    question: Question,
    draft: ArticleDraft,
    settings: Settings,
    *,
    task: TaskJob | None = None,
) -> ArticleQualityReview:
    opinion = await session.scalar(
        select(OpinionMap)
        .where(OpinionMap.question_id == question.id)
        .order_by(OpinionMap.version.desc())
        .limit(1)
    )
    version = await session.scalar(
        select(ArticleVersion).where(
            ArticleVersion.draft_id == draft.id,
            ArticleVersion.version == draft.current_version,
        )
    )
    if not opinion or not version:
        raise ValueError("文章版本或观点地图不存在")
    source_rows = (
        await session.scalars(
            select(ArticleParagraphSource).where(
                ArticleParagraphSource.article_version_id == version.id
            )
        )
    ).all()
    grouped: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"source_answer_ids": [], "cluster_ids": []}
    )
    for row in source_rows:
        if row.answer_id:
            grouped[row.paragraph_id]["source_answer_ids"].append(row.answer_id)
        if row.cluster_id:
            grouped[row.paragraph_id]["cluster_ids"].append(row.cluster_id)
    provider, _ = await _runtime_provider(session, settings)
    result = await ArticleReviewService(
        provider,
        await get_active_prompt(
            session, "article_quality_review", REVIEW_SYSTEM_PROMPT
        ) + "\n本稿是回答作者的观点调查，不是行业研究或对原问题的独立解答。核对 opinion_survey 中的程序统计、归类依据和样本边界；不要要求补写外部事实。未归类不等于反对。",
    ).review(
        question_title=question.title,
        article={
            "title": draft.title,
            "content": draft.content,
            "opinion_survey": version.source_snapshot.get("opinion_survey"),
            "source_answers": version.source_snapshot.get("answers", {}),
            "paragraphs": [
                {"paragraph_id": key, **value} for key, value in grouped.items()
            ],
        },
        opinion_map=opinion.content_json,
    )
    await record_model_usage(
        session,
        result.usage,
        question_id=question.id,
        task_id=task.id if task else None,
        stage="reviewing_article",
    )
    snapshot = version.source_snapshot or {}
    known_answers = set(snapshot.get("answers", {}))
    known_clusters = {item["id"] for item in snapshot.get("clusters", [])}
    source_issues = []
    for paragraph in snapshot.get("paragraphs", []):
        if set(paragraph.get("source_answer_ids", [])) - known_answers or set(paragraph.get("cluster_ids", [])) - known_clusters:
            source_issues.append("文章引用了不属于本次采集的来源")
        disclosure = paragraph.get("kind") == "disclosure" and len(paragraph.get("content", "")) <= 200
        if not paragraph.get("source_answer_ids") and not paragraph.get("cluster_ids") and not disclosure:
            source_issues.append("文章段落缺少来源关联")
        if paragraph.get("content") and paragraph["content"] not in draft.content and not snapshot.get("edited"):
            source_issues.append("段落来源映射与文章正文不一致")
    if source_issues:
        result.data.passed = False
        result.data.issues = list(dict.fromkeys(result.data.issues + source_issues))[:30]
        result.data.checks["source_integrity"] = False
    result.data.requires_human_review = True
    draft.review_result = result.data.model_dump()
    draft.reviewed_at = utc_now()
    draft.status = "waiting_review"
    question.status = "waiting_review"
    await session.commit()
    return result.data


async def rewrite_draft_text(
    session: AsyncSession,
    draft: ArticleDraft,
    settings: Settings,
    *,
    scope: str,
    text: str,
    instruction: str,
) -> str:
    question = await session.get(Question, draft.question_id)
    if not question:
        raise ValueError("草稿所属问题不存在")
    provider, _ = await _runtime_provider(session, settings)
    result = await DraftRewriteService(
        provider,
        await get_active_prompt(
            session, "draft_rewrite", REWRITE_SYSTEM_PROMPT
        ),
    ).rewrite(
        question_title=question.title,
        scope=scope,
        text=text,
        instruction=instruction,
    )
    await record_model_usage(
        session,
        result.usage,
        question_id=question.id,
        task_id=None,
        stage="draft_rewrite",
    )
    await session.commit()
    return result.data.text


async def usage_summary(
    session: AsyncSession, question_id: str
) -> dict[str, float | int]:
    row = (
        await session.execute(
            select(
                func.count(ModelUsageLog.id),
                func.coalesce(func.sum(ModelUsageLog.input_tokens), 0),
                func.coalesce(func.sum(ModelUsageLog.output_tokens), 0),
                func.coalesce(func.sum(ModelUsageLog.estimated_cost), 0),
                func.coalesce(func.sum(ModelUsageLog.duration_ms), 0),
            ).where(ModelUsageLog.question_id == question_id)
        )
    ).one()
    return {
        "calls": int(row[0]),
        "input_tokens": int(row[1]),
        "output_tokens": int(row[2]),
        "estimated_cost": float(row[3]),
        "duration_ms": int(row[4]),
    }
