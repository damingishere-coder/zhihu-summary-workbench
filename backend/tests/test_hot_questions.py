import pytest
from backend.app.db.session import get_session_factory
from backend.app.models.core import Question
from backend.app.services.hot_questions import receive_hot_result


@pytest.mark.asyncio
async def test_successful_hot_sync_retires_old_rank_without_deleting_question(app_client, monkeypatch):
    from backend.app.services import browser_bridge
    _, client, _ = app_client
    old = (await client.post('/api/questions/manual', json={'url':'https://www.zhihu.com/question/87654321','title':'昨天的热门问题'})).json()
    async with get_session_factory()() as session:
        row = await session.get(Question, old['id'])
        row.source = 'hot'
        row.hot_rank = 1
        await session.commit()
    class Bridge:
        connected_client_ids = {'test-hot'}
        async def send_control(self, client_id, message):
            receive_hot_result(client_id, message['nonce'], {'items':[{'id':'87654322','title':'今天的热门问题','rank':1}]})
            return True
    monkeypatch.setattr(browser_bridge, 'bridge_manager', Bridge())
    result = await client.post('/api/questions/hot/fetch', json={'limit':30})
    assert result.status_code == 200 and result.json()['created'] == 1
    async with get_session_factory()() as session:
        row = await session.get(Question, old['id'])
        assert row is not None and row.hot_rank is None
        assert row.title == '昨天的热门问题'
