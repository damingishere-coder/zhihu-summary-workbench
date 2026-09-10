from __future__ import annotations

import hashlib
import json
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from PIL import Image
from sqlalchemy import select

from backend.app.ai.providers.codex_image import CodexImageProvider, ImageResultUnknown, collect_artifact
from backend.app.ai.services.answer_chunks import chunks
from backend.app.core.config import get_settings
from backend.app.db.session import get_session_factory
from backend.app.models.browser_bridge import BrowserBridgeClient, CollectionJob
from backend.app.models.core import TaskJob, ArticleDraft, ArticleVersion
from backend.app.models.media import ImageVersion
from backend.app.services.capture_batches import save_capture_batch
from backend.app.services.checkpoints import recover_interrupted_tasks, resume_task
from backend.app.services.tasks import process_task
from backend.tests.test_browser_bridge import sample_v2_bundle
from backend.tests.test_task_flow import FakeZhihuCollector


async def queued_fixture(client, broker, external="76543210"):
    response = await client.post("/api/questions/manual", json={"url": f"https://www.zhihu.com/question/{external}", "title": "持续阅读的方法"})
    assert response.status_code == 201
    task = (await client.post(f"/api/questions/{response.json()['id']}/queue")).json()
    assert await broker.dequeue(timeout=.01) == task["id"]
    return task


@pytest.mark.asyncio
async def test_startup_holds_work_and_explicit_resume_retains_checkpoints(app_client):
    _, client, broker = app_client
    info = await queued_fixture(client, broker)
    async with get_session_factory()() as session:
        task = await session.get(TaskJob, info["id"])
        task.status = "generating_article"
        task.result = {"checkpoints": {"claims": {"claims": 17}}}
        await session.commit()
        assert await recover_interrupted_tasks(session) == 1
        await session.refresh(task)
        assert task.status == "paused"
        assert await broker.dequeue(timeout=.01) is None
        await resume_task(session, broker, task)
        assert task.result["checkpoints"]["claims"]["claims"] == 17
        assert await broker.dequeue(timeout=.01) == task.id


@pytest.mark.asyncio
async def test_batches_over_500_deduplicate_and_finalize_once(app_client):
    _, client, broker = app_client
    info = await queued_fixture(client, broker)
    factory = get_session_factory()
    await process_task(info["id"], worker_id="test", settings=get_settings(), broker=broker, session_factory=factory)
    async with factory() as session:
        job = await session.scalar(select(CollectionJob).where(CollectionJob.task_id == info["id"]))
        bridge = BrowserBridgeClient(token_hash="d" * 64, extension_version="0.3.0")
        session.add(bridge)
        await session.flush()
        job.client_id = bridge.id
        job.status = "dispatched"
        job.request_json = {**job.request_json, "read_all": True}
        await session.commit()
        args = {"client_id": bridge.id, "payload": {"job_id": job.id, "nonce": job.nonce}}
    bundle = sample_v2_bundle("76543210", count=300)
    for row in bundle["answers"]:
        row["voteup_count"] = 1
    args["payload"].update(bundle=bundle, elapsed_seconds=100)
    first = await save_capture_batch(factory, broker, **args)
    duplicate = await save_capture_batch(factory, broker, **args)
    assert first["saved"] == duplicate["saved"] == 300
    for row in bundle["answers"]:
        row["id"] = str(int(row["id"]) + 300)
    args["payload"].update(finished=True, stop_reason="page_end", elapsed_seconds=200)
    last = await save_capture_batch(factory, broker, **args)
    assert last["saved"] == 600 and last["completed"]
    again = await save_capture_batch(factory, broker, **args)
    assert again["saved"] == 600
    assert await broker.dequeue(timeout=.01) == info["id"]
    assert await broker.dequeue(timeout=.01) is None


@pytest.mark.asyncio
async def test_daily_plan_fills_from_manual_is_idempotent_and_pause_retains_ids(app_client):
    _, client, broker = app_client
    for number in range(3):
        await client.post("/api/questions/manual", json={"url": f"https://www.zhihu.com/question/{70000000 + number}", "title": "阅读习惯"})
    await client.patch("/api/plans/today", json={"question_limit": 3, "hot_quota": 2, "manual_quota": 1})
    first = await client.post("/api/plans/today/run")
    assert first.status_code == 200, first.text
    ids = first.json()["queued_task_ids"]
    assert len(ids) == 3
    again = await client.post("/api/plans/today/run")
    assert again.json()["queued_task_ids"] == []
    assert (await client.post("/api/plans/today/pause")).status_code == 200
    plan = (await client.get("/api/plans/today")).json()
    assert plan["result"]["queued_task_ids"] == ids
    assert plan["result"]["waiting"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason,expected", [("no_progress", "waiting_review"), ("", "paused")])
async def test_small_available_sample_continues_only_after_bounded_scroll_stop(app_client, stop_reason, expected):
    _, client, broker = app_client
    info = await queued_fixture(client, broker)
    class SmallSampleCollector(FakeZhihuCollector):
        async def fetch_question_and_answers(self, question_id, **kwargs):
            result = await super().fetch_question_and_answers(question_id, **kwargs)
            result.answers = result.answers[:5]
            result.capture = {"collected_answer_count": 5, "reached_end": False, "stop_reason": stop_reason}
            return result
    async with get_session_factory()() as session:
        task = await session.get(TaskJob, info["id"])
        task.payload = {**task.payload, "produce_images": True}
        await session.commit()
    await process_task(info["id"], worker_id="test", settings=get_settings(), broker=broker,
        session_factory=get_session_factory(), collector=SmallSampleCollector())
    task = (await client.get(f"/api/tasks/{info['id']}")).json()
    assert task["status"] == expected, task.get("error_message")
    if stop_reason:
        assert task["result"]["images_complete"]
        draft = (await client.get(f"/api/drafts/{task['result']['draft_id']}")).json()
        assert draft['analysis_snapshot']['capture']['stop_reason'] == 'no_progress'
        assert '仅代表样本' in draft['content']


def test_long_answer_chunks_include_the_tail():
    text = "甲" * 18001 + "独特的尾部反对意见"
    segments = chunks([{"answer_id": "a", "plain_content": text}])
    assert "".join(item["plain_content"] for item in segments) == text
    assert segments[-1]["source_end"] == len(text)


@pytest.mark.asyncio
async def test_uncertain_image_is_reconciled_without_new_submission(tmp_path, monkeypatch):
    folder = tmp_path / "task"
    folder.mkdir()
    home = tmp_path / "codex"
    thread = "12345678-1234-1234-1234-123456789abc"
    assets = home / "generated_images" / thread
    assets.mkdir(parents=True)
    Image.new("RGB", (300, 400), "white").save(assets / "image.png")
    (folder / "events.jsonl").write_text(json.dumps({"type": "thread.started", "thread_id": thread}), encoding="utf-8")
    (folder / "generation.json").write_text(json.dumps({"status": "unknown", "prompt_hash": hashlib.sha256(b"prompt").hexdigest()}), encoding="utf-8")
    settings = SimpleNamespace(codex_home=str(home))
    result = await CodexImageProvider(settings).generate("prompt", folder)
    assert result["width"] == 300
    assert json.loads((folder / "generation.json").read_text(encoding="utf-8"))["status"] == "completed"
    with pytest.raises(ImageResultUnknown):
        await CodexImageProvider(settings).generate("different prompt", folder)


@pytest.mark.asyncio
async def test_mock_pipeline_produces_rendered_package_and_rejects_stale_article(app_client, tmp_path, monkeypatch):
    _, client, broker = app_client
    info = await queued_fixture(client, broker)
    # Mock mode must render locally without submitting any real image request.
    async def fake_generate(self, prompt, folder):
        raise AssertionError('Mock mode must never submit real image generation')
    monkeypatch.setattr(CodexImageProvider, "generate", fake_generate)
    async with get_session_factory()() as session:
        task = await session.get(TaskJob, info["id"])
        task.payload = {**task.payload, "produce_images": True}
        await session.commit()
    await process_task(info["id"], worker_id="test", settings=get_settings(), broker=broker,
                       session_factory=get_session_factory(), collector=FakeZhihuCollector())
    task = (await client.get(f"/api/tasks/{info['id']}")).json()
    async with get_session_factory()() as session:
        render_diagnostics = [row.overflow_json for row in (await session.scalars(select(ImageVersion))).all()]
    assert task["status"] == "waiting_review", (task.get("error_message"), render_diagnostics)
    assert task["result"]["images_complete"]
    draft_id = task["result"]["draft_id"]
    assert (await client.post(f"/api/drafts/{draft_id}/approve")).status_code == 200
    package = await client.get(f"/api/drafts/{draft_id}/publish-package")
    assert package.status_code == 200, package.text if package.status_code != 200 else ""
    with ZipFile(BytesIO(package.content)) as archive:
        assert set(archive.namelist()) == {"article.md", "article.html", "infographic.png", "sources.json", "manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
        for name, checksum in manifest["sha256"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum
        assert json.loads(archive.read("sources.json"))["answers"]
    draft = (await client.get(f"/api/drafts/{draft_id}")).json()
    await client.patch(f"/api/drafts/{draft_id}", json={"title": draft["title"], "content": draft["content"] + "\n人工修改"})
    async with get_session_factory()() as session:
        row = await session.get(ArticleDraft, draft_id)
        row.status = "review_approved"
        await session.commit()
    stale = await client.get(f"/api/drafts/{draft_id}/publish-package")
    assert stale.status_code == 409 and "旧文章" in stale.text
