from copy import deepcopy

import pytest
from sqlalchemy import select

from backend.app.services.opinion_survey import author_key, build_survey, survey_paragraphs, combined_relation
from backend.app.services.survey_chart import survey_chart_html


def answer(identifier, author, included=True):
    return {'id': identifier, 'author_name': '同名用户',
            'author_url': f'https://www.zhihu.com/people/{author}' if author else '',
            'answer_url': f'https://www.zhihu.com/question/1/answer/{identifier}',
            'included_for_analysis': included}


def cluster(identifier, relations):
    return {'id': identifier, 'name': '保持低门槛', 'summary': '答主认为从小目标开始更容易持续。', 'source_relations': relations}


def test_unique_authors_conflicting_stances_unknowns_and_denominator():
    answers = [answer('1', 'alice'), answer('2', 'alice'), answer('3', 'bob'),
               answer('4', None), answer('5', None), answer('6', 'unclassified', False)]
    rows = [cluster('c1', {'1': 'supports', '2': 'opposes', '3': 'supports', '4': 'supports', '5': 'supports'}),
            cluster('c2', {'1': 'supports', '2': 'supports', '3': 'supports'})]
    survey = build_survey(answers, rows)
    assert survey['denominator'] == 3  # neither display names nor answer count
    assert survey['unidentified_answers'] == 2
    assert survey['unclassified_authors'] == 1
    assert survey['analyzed_answers'] == 5
    first = next(r for r in survey['rows'] if r['cluster_id'] == 'c1')
    second = next(r for r in survey['rows'] if r['cluster_id'] == 'c2')
    assert first['counts']['mixed'] == 1 and first['counts']['supports'] == 1
    assert first['support_percent'] == 33.3
    assert second['counts']['supports'] == 2 and second['support_percent'] == 66.7
    assert first['unidentified_answer_count'] == 2
    assert len(first['evidence']) == 5
    assert '占比不必合计100%' in survey['method']


def test_unknown_author_never_becomes_person_or_zero_percent():
    assert author_key('https://zhihu.com/people/alice/?utm_source=x') == 'people/alice'
    assert author_key('https://attacker.example/people/alice') is None
    assert author_key('https://www.zhihu.com/people/anonymous') is None
    result = build_survey([answer('1', None)], [cluster('c', {'1': 'supports'})])
    assert result['denominator'] == 0
    assert result['rows'][0]['support_percent'] is None
    assert '无法计算' in survey_paragraphs(result, ['1'])[1].content
    with pytest.raises(ValueError, match='未保存'):
        build_survey([], [cluster('c', {'missing': 'supports'})])


def test_chart_values_are_same_as_article_and_escape_labels():
    row = cluster('c', {'1': 'supports'})
    row['name'] = '<script>hello</script>'
    survey = build_survey([answer('1', 'alice'), answer('2', 'bob')], [row])
    html = survey_chart_html({'opinion_survey': survey, 'title': '观点'}, 1080, 1440)
    assert '1 人 · 50.0%' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '认同 1 人（50.0%）' in survey_paragraphs(survey, ['1', '2'])[1].content


def test_background_does_not_dilute_support_and_conditions_are_counted_explicitly():
    assert combined_relation({'supports', 'related'}) == 'supports'
    assert combined_relation({'conditional', 'opposes'}) == 'mixed'
    assert combined_relation({'mixed'}) == 'mixed'
    row = cluster('c', {'1': 'supports', '2': 'conditional', '3': 'opposes'})
    survey = build_survey([answer('1', 'a'), answer('2', 'b'), answer('3', 'c')], [row])
    assert survey['rows'][0]['endorsement_count'] == 2
    assert survey['rows'][0]['endorsement_percent'] == 66.7
    assert '认同 2 人（66.7%）' in survey_paragraphs(survey, ['1', '2', '3'])[1].content


@pytest.mark.asyncio
async def test_reassessment_keeps_short_views_and_preserves_manual_exclusions(app_client):
    from backend.app.db.session import get_session_factory
    from backend.app.models.content import Answer
    _, client, _ = app_client
    question = (await client.post('/api/questions/manual', json={
        'url': 'https://www.zhihu.com/question/12345678', 'title': '为什么不买车？'})).json()
    async with get_session_factory()() as session:
        for i, reason in enumerate(['内容过短', '内容哈希重复', '运营人员手动排除']):
            session.add(Answer(question_id=question['id'], answer_external_id=f'short-{i}',
                               content_hash='a' * 64,
                               plain_content='收入压力大，不想买车', included_for_analysis=False,
                               filter_reason=reason))
        await session.commit()
    result = await client.post(f"/api/questions/{question['id']}/evaluate")
    assert result.status_code == 200, result.text
    assert result.json()['counts'] == {'total': 3, 'included': 2, 'filtered': 1}
    async with get_session_factory()() as session:
        manual = await session.scalar(select(Answer).where(Answer.answer_external_id == 'short-2'))
        assert not manual.included_for_analysis and manual.filter_reason == '运营人员手动排除'


@pytest.mark.asyncio
async def test_article_and_image_use_frozen_survey_after_live_sources_change(app_client):
    from backend.tests.test_manual_production import queued_fixture
    from backend.tests.test_task_flow import FakeZhihuCollector
    from backend.app.core.config import get_settings
    from backend.app.db.session import get_session_factory
    from backend.app.services.tasks import process_task
    from backend.app.models.core import ArticleDraft, ArticleVersion
    from backend.app.models.content import Answer
    from backend.app.services.image_workflow import generate_infographic_content_version, update_infographic_version, get_image_workspace
    from backend.app.schemas.image import ImageEditorUpdate, InfographicContentData

    _, client, broker = app_client
    task = await queued_fixture(client, broker)
    await process_task(task['id'], worker_id='test', settings=get_settings(), broker=broker,
                       session_factory=get_session_factory(), collector=FakeZhihuCollector())
    result = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert result['status'] == 'waiting_review', result
    async with get_session_factory()() as session:
        draft = await session.get(ArticleDraft, result['result']['draft_id'])
        version = await session.scalar(select(ArticleVersion).where(ArticleVersion.draft_id == draft.id))
        frozen = deepcopy(version.source_snapshot['opinion_survey'])
        assert '## 各观点有多少人' in draft.content
        source = await session.scalar(select(Answer).where(Answer.question_id == draft.question_id))
        source.author_url = ''
        await session.commit()
        workspace = await generate_infographic_content_version(session, draft, get_settings(), template_type='knowledge_card', canvas_size='1080x1440')
        assert workspace.current.content_json['opinion_survey'] == frozen
        assert workspace.current.copy_state['article_version'] == draft.current_version
        image = await get_image_workspace(session, draft.id)
        edited = await update_infographic_version(session, image, ImageEditorUpdate(content=InfographicContentData.model_validate(workspace.current.content_json)))
        assert edited.current.content_json['opinion_survey'] == frozen
        from backend.app.services.image_workflow import generate_prompt_version
        next_survey = deepcopy(frozen)
        next_survey['rows'][0]['name'] = '新文章版本的观点标题'
        draft.current_version += 1
        session.add(ArticleVersion(draft_id=draft.id, version=draft.current_version,
                    title=draft.title, content=draft.content,
                    source_snapshot={**version.source_snapshot, 'opinion_survey': next_survey}))
        await session.commit()
        await session.refresh(draft, ['question'])
        prompted = await generate_prompt_version(session, draft, get_settings(), visual_style='简洁', aspect_ratio='3:4')
        assert prompted.current.content_json['opinion_survey'] == next_survey
        assert prompted.current.copy_state['article_version'] == draft.current_version
