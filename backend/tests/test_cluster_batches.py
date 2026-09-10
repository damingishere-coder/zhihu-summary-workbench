import hashlib
import struct

import pytest
from sqlalchemy import select

from backend.app.ai.providers.base import ProviderUsage, StructuredProviderResult
from backend.app.ai.services.content import ClusterRefinementService
from backend.app.core.config import get_settings
from backend.app.db.session import get_session_factory
from backend.app.models.core import Question, TaskJob
from backend.app.models.content import Answer, Claim, ClaimCluster, ClaimEmbedding
from backend.app.schemas.analysis import ClusterRefinement, ClusterRefinementItem, ClusterSourceRelation
from backend.app.services.cluster_batches import flatten_cluster_groups
from backend.app.services.content_pipeline import refine_clusters


def group(indexes, name='同一种观点', relation='supports'):
    return ClusterRefinementItem(source_cluster_indexes=indexes, name=name, summary=name,
        source_relations=[ClusterSourceRelation(source_cluster_index=i, relation=relation) for i in indexes],
        cluster_type='consensus', confidence=90, information_gain=80)


def test_global_merge_preserves_every_original_claim_and_does_not_guess_reversed_stances():
    initial = [group([0, 2]), group([1, 3])]
    merged = group([0, 1], '统一后的观点')
    merged.source_relations[1].relation = 'opposes'
    result = flatten_cluster_groups(initial, [merged], {0, 1, 2, 3})
    assert len(result) == 1
    assert set(result[0].source_cluster_indexes) == {0, 1, 2, 3}
    assert {r.source_cluster_index:r.relation for r in result[0].source_relations} == {
        0:'supports', 2:'supports', 1:'related', 3:'related'}


@pytest.mark.parametrize('indexes', [[0], [0, 0], [0, 2]])
def test_global_merge_rejects_missing_duplicate_or_unknown_directions(indexes):
    with pytest.raises(ValueError, match='跨批归并'):
        flatten_cluster_groups([group([0]), group([1])], [group(indexes)], {0, 1})


@pytest.mark.asyncio
async def test_multiple_refinement_batches_have_one_global_merge(app_client, monkeypatch):
    calls = []

    async def refined(self, *, question_title, rough_clusters):
        calls.append(len(rough_clusters))
        return StructuredProviderResult(
            data=ClusterRefinement(clusters=[group([r['index'] for r in rough_clusters])]),
            usage=ProviderUsage(provider='mock', model='mock', model_role='reasoning_model'))

    monkeypatch.setattr(ClusterRefinementService, 'refine', refined)
    async with get_session_factory()() as session:
        question = Question(external_id='99887766', title='观点跨批汇总',
            url='https://www.zhihu.com/question/99887766', content_hash='0' * 64)
        session.add(question)
        await session.flush()
        claim_ids = set()
        for i in range(65):
            content = f'作者 {i} 认为补贴使购车需求提前释放。'
            digest = hashlib.sha256(content.encode()).hexdigest()
            answer = Answer(question_id=question.id, answer_external_id=f'cross-batch-{i}',
                content_hash=digest, plain_content=content)
            session.add(answer)
            await session.flush()
            claim = Claim(question_id=question.id, answer_id=answer.id, content=content, content_hash=digest)
            session.add(claim)
            await session.flush()
            claim_ids.add(claim.id)
            session.add(ClaimEmbedding(claim_id=claim.id, content_hash=digest, provider='local',
                model='test', dimensions=2, vector=struct.pack('<ff', 1, 0)))
        task = TaskJob(question_id=question.id, status='refining_clusters', stage='refining_clusters', progress=70)
        session.add(task)
        await session.commit()
        await refine_clusters(session, question, get_settings(), task=task)
        clusters = (await session.scalars(select(ClaimCluster).where(ClaimCluster.question_id == question.id))).all()
        assert calls == [64, 1, 2]
        assert len(clusters) == 1
        assert set(clusters[0].metadata_json['claim_ids']) == claim_ids
        assert task.progress == 76
