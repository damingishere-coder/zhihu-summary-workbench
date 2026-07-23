from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_db_session
from backend.app.models.content import (
    Answer,
    Claim,
    ClaimCluster,
    ClusterAnswerLink,
    OpinionMap,
)
from backend.app.models.core import ArticleDraft, Question
from backend.app.schemas.analysis import (
    AnalysisOverview,
    ClusterMergeRequest,
    ClusterRead,
    ClusterSplitRequest,
    ClusterUpdate,
    OpinionMapData,
    StageRunResponse,
)
from backend.app.schemas.draft import DraftRead
from backend.app.services.content_pipeline import (
    cluster_rows,
    evaluate_answers,
    extract_claims,
    generate_article,
    generate_embeddings,
    generate_opinion_map,
    refine_clusters,
    reanalyze_cluster,
    review_article,
    usage_summary,
)
from backend.app.services.serializers import draft_to_read


router = APIRouter(tags=["analysis"])


async def _question(session: AsyncSession, question_id: str) -> Question:
    item = await session.get(Question, question_id)
    if not item:
        raise HTTPException(status_code=404, detail="问题不存在")
    return item


def _stage_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.post(
    "/questions/{question_id}/evaluate", response_model=StageRunResponse
)
async def run_evaluation(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> StageRunResponse:
    question = await _question(session, question_id)
    try:
        counts = await evaluate_answers(session, question, settings)
    except (ValueError, RuntimeError) as exc:
        raise _stage_error(exc) from exc
    return StageRunResponse(
        stage="evaluating_answers",
        message="回答质量筛选完成",
        counts=counts,
        usage=await usage_summary(session, question_id),
    )


@router.post(
    "/questions/{question_id}/extract-claims", response_model=StageRunResponse
)
async def run_claim_extraction(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> StageRunResponse:
    question = await _question(session, question_id)
    try:
        counts = await extract_claims(session, question, settings)
    except (ValueError, RuntimeError) as exc:
        raise _stage_error(exc) from exc
    return StageRunResponse(
        stage="extracting_claims",
        message="回答观点提取完成",
        counts=counts,
        usage=await usage_summary(session, question_id),
    )


@router.post(
    "/questions/{question_id}/generate-embeddings",
    response_model=StageRunResponse,
)
async def run_embeddings(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> StageRunResponse:
    question = await _question(session, question_id)
    try:
        counts = await generate_embeddings(session, question, settings)
    except (ValueError, RuntimeError) as exc:
        raise _stage_error(exc) from exc
    return StageRunResponse(
        stage="generating_embeddings",
        message="观点 Embedding 已生成",
        counts=counts,
    )


@router.post("/questions/{question_id}/cluster", response_model=StageRunResponse)
async def run_clustering(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> StageRunResponse:
    question = await _question(session, question_id)
    try:
        counts = await refine_clusters(session, question, settings)
    except (ValueError, RuntimeError) as exc:
        raise _stage_error(exc) from exc
    return StageRunResponse(
        stage="refining_clusters",
        message="粗聚类和聚类修正完成",
        counts=counts,
        usage=await usage_summary(session, question_id),
    )


@router.post(
    "/questions/{question_id}/generate-opinion-map",
    response_model=OpinionMapData,
)
async def run_opinion_map(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> OpinionMapData:
    question = await _question(session, question_id)
    try:
        item = await generate_opinion_map(session, question, settings)
    except (ValueError, RuntimeError) as exc:
        raise _stage_error(exc) from exc
    return OpinionMapData.model_validate(item.content_json)


@router.get("/questions/{question_id}/clusters", response_model=list[ClusterRead])
async def get_clusters(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[ClusterRead]:
    await _question(session, question_id)
    return [ClusterRead.model_validate(item) for item in await cluster_rows(session, question_id)]


@router.get("/questions/{question_id}/analysis", response_model=AnalysisOverview)
async def get_analysis_overview(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisOverview:
    await _question(session, question_id)
    total = int(
        (
            await session.scalar(
                select(func.count(Answer.id)).where(Answer.question_id == question_id)
            )
        )
        or 0
    )
    included = int(
        (
            await session.scalar(
                select(func.count(Answer.id)).where(
                    Answer.question_id == question_id,
                    Answer.included_for_analysis.is_(True),
                )
            )
        )
        or 0
    )
    opinion = await session.scalar(
        select(OpinionMap)
        .where(OpinionMap.question_id == question_id)
        .order_by(OpinionMap.version.desc())
        .limit(1)
    )
    draft_id = await session.scalar(
        select(ArticleDraft.id)
        .where(ArticleDraft.question_id == question_id)
        .order_by(ArticleDraft.updated_at.desc())
        .limit(1)
    )
    return AnalysisOverview(
        question_id=question_id,
        answers_total=total,
        answers_included=included,
        clusters=[
            ClusterRead.model_validate(item)
            for item in await cluster_rows(session, question_id)
        ],
        opinion_map=(
            OpinionMapData.model_validate(opinion.content_json) if opinion else None
        ),
        opinion_map_version=opinion.version if opinion else None,
        model_usage=await usage_summary(session, question_id),
        latest_draft_id=draft_id,
    )


async def _cluster_read(
    session: AsyncSession, cluster_id: str
) -> ClusterRead:
    cluster = await session.get(ClaimCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="观点簇不存在")
    rows = await cluster_rows(session, cluster.question_id)
    return ClusterRead.model_validate(next(item for item in rows if item["id"] == cluster_id))


@router.patch("/clusters/{cluster_id}", response_model=ClusterRead)
async def patch_cluster(
    cluster_id: str,
    payload: ClusterUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> ClusterRead:
    cluster = await session.get(ClaimCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="观点簇不存在")
    values = payload.model_dump(exclude_none=True)
    metadata = dict(cluster.metadata_json or {})
    for key in ("sort_order", "write_policy"):
        if key in values:
            metadata[key] = values.pop(key)
    cluster.metadata_json = metadata
    for key, value in values.items():
        setattr(cluster, key, value)
    await session.commit()
    return await _cluster_read(session, cluster_id)


@router.post("/clusters/{cluster_id}/reanalyze", response_model=ClusterRead)
async def run_cluster_reanalysis(
    cluster_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ClusterRead:
    cluster = await session.get(ClaimCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="观点簇不存在")
    try:
        await reanalyze_cluster(session, cluster, settings)
    except (ValueError, RuntimeError) as exc:
        raise _stage_error(exc) from exc
    return await _cluster_read(session, cluster_id)


@router.post("/clusters/merge", response_model=ClusterRead)
async def merge_clusters(
    payload: ClusterMergeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ClusterRead:
    clusters = list(
        (
            await session.scalars(
                select(ClaimCluster).where(
                    ClaimCluster.id.in_(payload.cluster_ids)
                )
            )
        ).all()
    )
    if len(clusters) != len(set(payload.cluster_ids)):
        raise HTTPException(status_code=404, detail="部分观点簇不存在")
    question_ids = {item.question_id for item in clusters}
    if len(question_ids) != 1:
        raise HTTPException(status_code=409, detail="只能合并同一问题的观点簇")
    source_rows = [
        item
        for cluster in clusters
        for item in await cluster_rows(session, cluster.question_id)
        if item["id"] == cluster.id
    ]
    answer_ids = list(
        dict.fromkeys(
            value for item in source_rows for value in item["source_answer_ids"]
        )
    )
    claim_ids = list(
        dict.fromkeys(value for item in source_rows for value in item["claim_ids"])
    )
    merged = ClaimCluster(
        question_id=clusters[0].question_id,
        name=payload.name or " / ".join(item.name for item in clusters)[:300],
        summary="；".join(item.summary for item in clusters)[:4000],
        cluster_type="consensus"
        if any(item.is_mainstream for item in clusters)
        else clusters[0].cluster_type,
        confidence=max(item.confidence for item in clusters),
        support_count=len(answer_ids),
        opposing_reasons=list(
            dict.fromkeys(
                value for item in clusters for value in item.opposing_reasons
            )
        ),
        applicable_conditions=list(
            dict.fromkeys(
                value for item in clusters for value in item.applicable_conditions
            )
        ),
        is_mainstream=any(item.is_mainstream for item in clusters),
        is_minority=all(item.is_minority for item in clusters),
        is_controversial=any(item.is_controversial for item in clusters),
        information_gain=max(item.information_gain for item in clusters),
        metadata_json={
            "claim_ids": claim_ids,
            "manually_merged": True,
            "sort_order": min(item["sort_order"] for item in source_rows),
            "write_policy": (
                "force"
                if any(item["write_policy"] == "force" for item in source_rows)
                else "auto"
            ),
        },
    )
    session.add(merged)
    await session.flush()
    for answer_id in answer_ids:
        session.add(
            ClusterAnswerLink(
                cluster_id=merged.id, answer_id=answer_id, relation="supports"
            )
        )
    for claim in (
        await session.scalars(select(Claim).where(Claim.id.in_(claim_ids)))
    ).all():
        claim.metadata_json = {**claim.metadata_json, "cluster_id": merged.id}
    await session.execute(
        delete(ClusterAnswerLink).where(
            ClusterAnswerLink.cluster_id.in_(payload.cluster_ids)
        )
    )
    await session.execute(
        delete(ClaimCluster).where(ClaimCluster.id.in_(payload.cluster_ids))
    )
    await session.commit()
    return await _cluster_read(session, merged.id)


@router.post("/clusters/{cluster_id}/split", response_model=ClusterRead)
async def split_cluster(
    cluster_id: str,
    payload: ClusterSplitRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ClusterRead:
    cluster = await session.get(ClaimCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="观点簇不存在")
    current_claim_ids = list((cluster.metadata_json or {}).get("claim_ids", []))
    if not set(payload.claim_ids).issubset(current_claim_ids):
        raise HTTPException(status_code=409, detail="拆分观点不属于该观点簇")
    claims = list(
        (
            await session.scalars(
                select(Claim).where(Claim.id.in_(payload.claim_ids))
            )
        ).all()
    )
    answer_ids = list(dict.fromkeys(item.answer_id for item in claims))
    split = ClaimCluster(
        question_id=cluster.question_id,
        name=payload.name,
        summary="；".join(item.content for item in claims)[:4000],
        cluster_type="minority",
        confidence=cluster.confidence,
        support_count=len(answer_ids),
        is_minority=True,
        information_gain=cluster.information_gain,
        metadata_json={
            "claim_ids": payload.claim_ids,
            "manually_split": True,
            "sort_order": int(
                (cluster.metadata_json or {}).get("sort_order", 0)
            )
            + 1,
            "write_policy": "auto",
        },
    )
    session.add(split)
    await session.flush()
    cluster.metadata_json = {
        **(cluster.metadata_json or {}),
        "claim_ids": [
            item for item in current_claim_ids if item not in payload.claim_ids
        ],
    }
    for answer_id in answer_ids:
        session.add(
            ClusterAnswerLink(
                cluster_id=split.id, answer_id=answer_id, relation="supports"
            )
        )
    for claim in claims:
        claim.metadata_json = {**claim.metadata_json, "cluster_id": split.id}
    await session.commit()
    return await _cluster_read(session, split.id)


@router.delete("/clusters/{cluster_id}", status_code=204)
async def delete_cluster(
    cluster_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    cluster = await session.get(ClaimCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="观点簇不存在")
    await session.execute(
        delete(ClusterAnswerLink).where(
            ClusterAnswerLink.cluster_id == cluster_id
        )
    )
    await session.delete(cluster)
    await session.commit()


@router.post("/questions/{question_id}/generate-draft", response_model=DraftRead)
async def run_generate_draft(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DraftRead:
    question = await _question(session, question_id)
    try:
        draft, _ = await generate_article(session, question, settings)
        await review_article(session, question, draft, settings)
    except (ValueError, RuntimeError) as exc:
        raise _stage_error(exc) from exc
    draft = await session.scalar(
        select(ArticleDraft)
        .options(selectinload(ArticleDraft.question))
        .where(ArticleDraft.id == draft.id)
    )
    return draft_to_read(draft)
