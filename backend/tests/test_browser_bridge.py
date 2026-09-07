from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from backend.app.core.config import get_settings
from backend.app.db.session import get_session_factory
from backend.app.models.browser_bridge import BrowserBridgeClient, CollectionJob
from backend.app.models.content import Answer, Claim, ClaimCluster, OpinionMap
from backend.app.models.core import ArticleDraft, ModelUsageLog
from backend.app.schemas.browser_bridge import CollectionBundleV2, ImportBundleV1
from backend.app.services.browser_bridge import (
    bridge_manager,
    bundle_to_fetch_result,
    complete_collection_job,
    fail_collection_job,
)
from backend.app.services.tasks import process_task
from backend.app.api.routes.browser_bridge import bridge_origin_allowed


def sample_bundle(question_id: str, *, count: int = 5) -> dict[str, object]:
    return {
        "format": "ImportBundleV1",
        "version": 1,
        "collected_at": "2026-08-23T12:00:00Z",
        "mode": "representative",
        "question": {
            "id": question_id,
            "title": "Chrome 扩展桥接的真实任务测试",
            "url": f"https://www.zhihu.com/question/{question_id}",
            "detail": "用于验证扩展采集完成后继续摘要流水线。",
            "answer_count": count,
            "follower_count": 9,
        },
        "answers": [
            {
                "id": str(900000 + index),
                "question_id": question_id,
                "author": {"name": f"作者{index}", "url_token": f"author-{index}"},
                "content": (
                    f"<p>第 {index} 条回答提供一个明确观点，并包含足够长的原因、条件、例子和限制，"
                    "用于验证真实清洗、分析、聚类与草稿流程。</p>"
                ),
                "voteup_count": 100 - index,
                "comment_count": index,
                "created_time": 1_700_000_000 + index,
                "updated_time": 1_700_000_100 + index,
            }
            for index in range(count)
        ],
        "warnings": [],
    }


def sample_v2_bundle(question_id: str, *, count: int = 5) -> dict[str, object]:
    bundle = sample_bundle(question_id, count=count)
    bundle["format"] = "CollectionBundleV2"
    bundle["version"] = 2
    bundle["capture"] = {
        "method": "rendered_dom",
        "page_url": f"https://www.zhihu.com/question/{question_id}",
        "visible_answer_count": count + 2,
        "collected_answer_count": count,
        "diagnostics": [
            {"code": "dom_capture", "level": "info", "message": "DOM fixture"}
        ],
    }
    return bundle


def test_websocket_origin_is_limited_to_extension_and_loopback() -> None:
    assert bridge_origin_allowed("chrome-extension://abcdefghijklmnopabcdefghijklmnop")
    assert bridge_origin_allowed("http://127.0.0.1:4173")
    assert bridge_origin_allowed("http://localhost:4173")
    assert not bridge_origin_allowed("https://evil.example")
    assert not bridge_origin_allowed(None)


@pytest.mark.asyncio
async def test_pairing_is_one_time_and_only_token_hash_is_persisted(app_client) -> None:
    _, client, _ = app_client
    pairing = await client.post("/api/settings/browser/bridge/pairing")
    assert pairing.status_code == 200
    code = pairing.json()["pairing_code"]
    token = None
    async with get_session_factory()() as session:
        bridge_client, token = await bridge_manager.authenticate_hello(
            session,
            {
                "protocol_version": 1,
                "extension_version": "0.1.0",
                "pairing_code": code,
            },
        )
        assert token
        assert bridge_client.token_hash != token
        assert len(bridge_client.token_hash) == 64
    async with get_session_factory()() as session:
        with pytest.raises(ValueError, match="无效或已过期"):
            await bridge_manager.authenticate_hello(
                session,
                {
                    "protocol_version": 1,
                    "extension_version": "0.1.0",
                    "pairing_code": code,
                },
            )
        authenticated, issued = await bridge_manager.authenticate_hello(
            session,
            {
                "protocol_version": 1,
                "extension_version": "0.1.0",
                "token": token,
            },
        )
        assert authenticated.id == bridge_client.id
        assert issued is None


@pytest.mark.asyncio
async def test_expired_pairing_and_wrong_token_are_rejected(app_client) -> None:
    _, client, _ = app_client
    code = (await client.post("/api/settings/browser/bridge/pairing")).json()["pairing_code"]
    bridge_manager._pairings[code].expires_at -= timedelta(minutes=11)
    async with get_session_factory()() as session:
        with pytest.raises(ValueError, match="过期"):
            await bridge_manager.authenticate_hello(
                session,
                {"protocol_version": 1, "extension_version": "0.1.0", "pairing_code": code},
            )
        with pytest.raises(ValueError, match="令牌无效"):
            await bridge_manager.authenticate_hello(
                session,
                {"protocol_version": 1, "extension_version": "0.1.0", "token": "wrong"},
            )


def test_bridge_payload_is_recleaned_and_dangerous_html_is_removed() -> None:
    raw = sample_bundle("12345678", count=1)
    raw["answers"][0]["content"] = (
        '<script>alert("secret")</script><p onclick="steal()">安全正文足够长，'
        '用于验证后端重新清洗不可信网页内容。</p><a href="javascript:steal()">危险链接</a>'
    )
    bundle = ImportBundleV1.model_validate(raw)
    result = bundle_to_fetch_result(bundle, collector_mode="chrome_extension")
    answer = result.answers[0]
    assert "<script" not in answer.html_content
    assert "onclick" not in answer.html_content
    assert "javascript:" not in answer.html_content
    assert "alert" not in answer.plain_content
    assert "安全正文" in answer.plain_content


def test_import_bundle_rejects_duplicates_and_cross_question_answers() -> None:
    duplicate = sample_bundle("12345678", count=2)
    duplicate["answers"][1]["id"] = duplicate["answers"][0]["id"]
    with pytest.raises(ValueError, match="重复"):
        ImportBundleV1.model_validate(duplicate)
    wrong_question = sample_bundle("12345678", count=1)
    wrong_question["answers"][0]["question_id"] = "87654321"
    with pytest.raises(ValueError, match="不一致"):
        ImportBundleV1.model_validate(wrong_question)


def test_collection_bundle_v2_validates_capture_counts() -> None:
    bundle = CollectionBundleV2.model_validate(sample_v2_bundle("12345678", count=2))
    assert bundle.capture.method == "rendered_dom"
    assert bundle.capture.visible_answer_count == 4
    mismatched = sample_v2_bundle("12345678", count=2)
    mismatched["capture"]["collected_answer_count"] = 1
    with pytest.raises(ValueError, match="采集统计"):
        CollectionBundleV2.model_validate(mismatched)
    external_page = sample_v2_bundle("12345678", count=1)
    external_page["capture"]["page_url"] = "javascript:alert(1)"
    with pytest.raises(ValueError, match="知乎 HTTPS"):
        CollectionBundleV2.model_validate(external_page)


@pytest.mark.asyncio
async def test_json_import_is_labeled_and_resumes_waiting_task(app_client) -> None:
    _, client, broker = app_client
    created = await client.post(
        "/api/questions/manual",
        json={
            "url": "https://www.zhihu.com/question/77889900/answer/123456789",
            "title": "JSON 导入恢复测试",
        },
    )
    question_id = created.json()["id"]
    queued = await client.post(f"/api/questions/{question_id}/queue")
    task_id = queued.json()["id"]
    assert await broker.dequeue(timeout=1) == task_id
    await process_task(
        task_id,
        worker_id="import-test-worker",
        settings=get_settings(),
        broker=broker,
        session_factory=get_session_factory(),
    )
    imported = await client.post(
        f"/api/questions/{question_id}/answers/import",
        json=sample_bundle("77889900"),
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 5
    assert imported.json()["resumed_task_id"] == task_id
    question = await client.get(f"/api/questions/{question_id}")
    assert question.json()["url"] == "https://www.zhihu.com/question/77889900"
    detail = await client.get(f"/api/tasks/{task_id}")
    assert detail.json()["status"] == "queued"
    assert detail.json()["retry_count"] == 0
    assert "不代表实时自动采集成功" in detail.json()["logs"][-1]["message"]
    async with get_session_factory()() as session:
        job = await session.scalar(
            select(CollectionJob).where(
                CollectionJob.task_id == task_id,
                CollectionJob.source == "import",
            )
        )
        assert job is not None


@pytest.mark.asyncio
async def test_health_reports_latest_uncached_real_model_usage(app_client) -> None:
    _, client, _ = app_client
    async with get_session_factory()() as session:
        session.add(
            ModelUsageLog(
                provider="codex",
                model_role="analysis",
                model="gpt-5.6-sol",
                stage="claim_extraction",
                status="success",
                cache_hit=False,
            )
        )
        await session.commit()

    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["model"]["last_real_validation"] == {
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "stage": "claim_extraction",
        "verified_at": response.json()["model"]["last_real_validation"]["verified_at"],
    }


@pytest.mark.asyncio
async def test_simulated_extension_completion_reaches_waiting_review(app_client) -> None:
    _, client, broker = app_client
    created = await client.post(
        "/api/questions/manual",
        json={
            "url": "https://www.zhihu.com/question/58173613",
            "title": "扩展桥接端到端测试问题",
        },
    )
    question_id = created.json()["id"]
    queued = await client.post(f"/api/questions/{question_id}/queue")
    task_id = queued.json()["id"]
    assert await broker.dequeue(timeout=1) == task_id

    await process_task(
        task_id,
        worker_id="bridge-test-worker",
        settings=get_settings(),
        broker=broker,
        session_factory=get_session_factory(),
    )
    waiting = await client.get(f"/api/tasks/{task_id}")
    assert waiting.json()["status"] == "waiting_browser"
    assert waiting.json()["retry_count"] == 0

    async with get_session_factory()() as session:
        job = await session.scalar(select(CollectionJob).where(CollectionJob.task_id == task_id))
        bridge_client = BrowserBridgeClient(
            token_hash="a" * 64,
            status="paired",
            extension_version="0.1.0",
        )
        other_client = BrowserBridgeClient(
            token_hash="c" * 64,
            status="paired",
            extension_version="0.2.0",
        )
        session.add_all([bridge_client, other_client])
        await session.flush()
        job.client_id = bridge_client.id
        job.status = "dispatched"
        await session.commit()
        client_id = bridge_client.id
        other_client_id = other_client.id
        job_id = job.id
        nonce = job.nonce

    with pytest.raises(ValueError, match="nonce"):
        await complete_collection_job(
            get_session_factory(),
            broker,
            client_id=client_id,
            job_id=job_id,
            nonce="wrong-nonce",
            bundle_payload=sample_v2_bundle("58173613"),
        )
    with pytest.raises(ValueError, match="不是该采集任务"):
        await complete_collection_job(
            get_session_factory(),
            broker,
            client_id=other_client_id,
            job_id=job_id,
            nonce=nonce,
            bundle_payload=sample_v2_bundle("58173613"),
        )
    result = await complete_collection_job(
        get_session_factory(),
        broker,
        client_id=client_id,
        job_id=job_id,
        nonce=nonce,
        bundle_payload=sample_v2_bundle("58173613"),
    )
    assert result == "completed"
    duplicate = await complete_collection_job(
        get_session_factory(),
        broker,
        client_id=client_id,
        job_id=job_id,
        nonce=nonce,
        bundle_payload=sample_v2_bundle("58173613"),
    )
    assert duplicate == "duplicate"
    assert await broker.dequeue(timeout=1) == task_id
    assert await broker.dequeue(timeout=0.01) is None

    await process_task(
        task_id,
        worker_id="bridge-test-worker-2",
        settings=get_settings(),
        broker=broker,
        session_factory=get_session_factory(),
    )
    completed = await client.get(f"/api/tasks/{task_id}")
    assert completed.json()["status"] == "waiting_review"
    assert completed.json()["result"]["collector_mode"] == "chrome_extension"
    assert completed.json()["result"]["capture"] == {
        "method": "rendered_dom",
        "page_url": "https://www.zhihu.com/question/58173613",
        "visible_answer_count": 7,
        "collected_answer_count": 5,
        "diagnostics": [
            {"code": "dom_capture", "level": "info", "message": "DOM fixture"}
        ],
        "version": 2,
        "stop_reason": "", "elapsed_seconds": 0.0, "reached_end": False,
    }
    async with get_session_factory()() as session:
        assert await session.scalar(select(func.count(Answer.id))) == 5
        assert await session.scalar(select(func.count(Claim.id))) > 0
        assert await session.scalar(select(func.count(ClaimCluster.id))) > 0
        assert await session.scalar(select(func.count(OpinionMap.id))) == 1
        assert await session.scalar(select(func.count(ArticleDraft.id))) == 1
        assert await session.scalar(select(func.count(ModelUsageLog.id))) > 0
        persisted_job = await session.get(CollectionJob, job_id)
        assert persisted_job.capture_version == 2
        assert persisted_job.capture_method == "rendered_dom"
        assert persisted_job.visible_answer_count == 7
        assert persisted_job.collected_answer_count == 5


@pytest.mark.asyncio
async def test_failed_dom_capture_persists_diagnostics_without_retry(app_client) -> None:
    _, client, broker = app_client
    question_id = (
        await client.post(
            "/api/questions/manual",
            json={"url": "https://www.zhihu.com/question/44556677", "title": "DOM 变化测试"},
        )
    ).json()["id"]
    task_id = (await client.post(f"/api/questions/{question_id}/queue")).json()["id"]
    assert await broker.dequeue(timeout=1) == task_id
    await process_task(
        task_id,
        worker_id="dom-failure-worker",
        settings=get_settings(),
        broker=broker,
        session_factory=get_session_factory(),
    )
    async with get_session_factory()() as session:
        job = await session.scalar(select(CollectionJob).where(CollectionJob.task_id == task_id))
        bridge_client = BrowserBridgeClient(
            token_hash="b" * 64,
            status="paired",
            extension_version="0.2.0",
        )
        session.add(bridge_client)
        await session.commit()
        job_id = job.id
        nonce = job.nonce
        client_id = bridge_client.id
    await fail_collection_job(
        get_session_factory(),
        broker,
        client_id=client_id,
        job_id=job_id,
        nonce=nonce,
        message="未识别回答结构",
        capture={
            "method": "rendered_dom",
            "page_url": "https://www.zhihu.com/question/44556677",
            "visible_answer_count": 2,
            "collected_answer_count": 0,
            "diagnostics": [
                {
                    "code": "answer_structure_changed",
                    "level": "error",
                    "message": "页面结构发生变化",
                }
            ],
        },
    )
    detail = (await client.get(f"/api/tasks/{task_id}")).json()
    assert detail["status"] == "waiting_browser"
    assert detail["retry_count"] == 0
    assert detail["result"]["capture"]["recommended_action"] == (
        "retry_visible_page_or_import_json"
    )
    async with get_session_factory()() as session:
        job = await session.get(CollectionJob, job_id)
        assert job.status == "failed"
        assert job.capture_method == "rendered_dom"
        assert job.capture_diagnostics_json[0]["code"] == "answer_structure_changed"
    bridge_status = (await client.get("/api/settings/browser/bridge")).json()
    assert bridge_status["latest_capture"] == {
        "job_id": job_id,
        "status": "failed",
        "source": "extension",
        "capture_version": 2,
        "capture_method": "rendered_dom",
        "page_url": "https://www.zhihu.com/question/44556677",
        "visible_answer_count": 2,
        "collected_answer_count": 0,
        "diagnostics": [
            {
                "code": "answer_structure_changed",
                "level": "error",
                "message": "页面结构发生变化",
            }
        ],
    }
