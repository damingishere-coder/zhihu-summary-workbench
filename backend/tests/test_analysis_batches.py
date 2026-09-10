import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.models.core import ModelResponseCache, ModelUsageLog, Question, SystemSetting, TaskJob, TaskLog
from backend.app.models.content import AnswerAnalysis, Claim
from backend.app.ai.services.content import AnswerQualityService, AnswerClaimBatchService
from backend.app.schemas.analysis import FetchAnswersRequest
from backend.app.services.content_pipeline import evaluate_answers, extract_claims, fetch_and_store_answers
from backend.app.services.checkpoints import PipelinePaused
from backend.tests.test_task_flow import FakeZhihuCollector


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_mode', ['model_error', 'pause'])
@pytest.mark.parametrize('stage,service,method,run', [
    ('evaluating_answers', AnswerQualityService, 'evaluate_batch', evaluate_answers),
    ('extracting_claims', AnswerClaimBatchService, 'extract_batch', extract_claims),
])
async def test_completed_batch_is_durable_and_unlocks_database_before_next_request(
    tmp_path, monkeypatch, stage, service, method, run, failure_mode,
):
    engine = create_async_engine(f'sqlite+aiosqlite:///{(tmp_path / "batches.db").as_posix()}',
                                 connect_args={'timeout': .1})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = get_settings().model_copy(update={'answer_quality_batch_size': 2, 'claim_extraction_batch_size': 2})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            question = Question(external_id='87654321', title='运动习惯',
                url='https://www.zhihu.com/question/87654321', content_hash='0' * 64)
            session.add(question)
            await session.commit()
            fetched = await FakeZhihuCollector().fetch_question_and_answers(question.external_id)
            fetched.answers = fetched.answers[:4]
            await fetch_and_store_answers(session, question, settings, FetchAnswersRequest(), precollected=fetched)
            task = TaskJob(question_id=question.id, status=stage, stage=stage)
            session.add(task)
            await session.commit()
            task_id, question_id = task.id, question.id
            original = getattr(service, method)
            calls = 0

            async def fail_second_batch(self, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    async with factory() as observer:
                        assert await observer.scalar(select(func.count(ModelUsageLog.id))) == 1
                        assert await observer.scalar(select(func.count(ModelResponseCache.id))) == 1
                        assert await observer.scalar(select(func.count(AnswerAnalysis.id))) == 2
                        observer.add(SystemSetting(key='concurrent-write', value='available'))
                        await observer.commit()
                    raise RuntimeError('second batch failed')
                response = await original(self, **kwargs)
                if failure_mode == 'pause':
                    task.payload = {**task.payload, 'pause_requested': True}
                return response

            monkeypatch.setattr(service, method, fail_second_batch)
            expected_error = PipelinePaused if failure_mode == 'pause' else RuntimeError
            with pytest.raises(expected_error):
                await run(session, question, settings, task=task)
            assert calls == (1 if failure_mode == 'pause' else 2)
            await session.rollback()

        async with factory() as session:
            assert await session.scalar(select(func.count(ModelUsageLog.id))) == 1
            log = await session.scalar(select(TaskLog).where(TaskLog.task_id == task_id))
            assert log.metadata_json == {'completed': 2, 'total': 4}
            if stage == 'extracting_claims':
                assert await session.scalar(select(func.count(Claim.id))) > 0
            monkeypatch.setattr(service, method, original)
            resumed_task = await session.get(TaskJob, task_id)
            resumed_task.payload = {**resumed_task.payload, 'pause_requested': False}
            await session.commit()
            await run(session, await session.get(Question, question_id), settings,
                      task=resumed_task)
            assert await session.scalar(select(func.count(AnswerAnalysis.id))) == 4
            assert await session.scalar(select(func.count(ModelUsageLog.id)).where(ModelUsageLog.cache_hit.is_(True))) == 1
    finally:
        await engine.dispose()
