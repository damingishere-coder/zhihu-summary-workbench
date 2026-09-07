"""Acknowledge only committed batches. Retrying a batch is idempotent."""
from __future__ import annotations

import asyncio
import secrets
from typing import Any

from backend.app.models.browser_bridge import CollectionJob
from backend.app.models.core import TaskJob, Question
from sqlalchemy import update
from backend.app.models.common import utc_now
from backend.app.schemas.browser_bridge import CollectionBundleV2, CollectionBundleV3
from backend.app.services.browser_bridge import complete_collection_job


_lock = asyncio.Lock()


async def save_capture_batch(factory, broker, *, client_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with _lock:
        return await _save(factory, broker, client_id=client_id, payload=payload)


async def _save(factory, broker, *, client_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id", ""))
    nonce = str(payload.get("nonce", ""))
    async with factory() as session:
        job = await session.get(CollectionJob, job_id)
        if not job or not secrets.compare_digest(job.nonce, nonce) or job.client_id != client_id:
            raise ValueError("采集批次身份无效")
        if job.status == "completed":
            return {"continue": False, "saved": job.collected_answer_count, "completed": True}
        if job.status not in {"pending", "dispatched"}:
            return {"continue": False, "saved": job.collected_answer_count or 0, "reason": job.status}
        task = await session.get(TaskJob, job.task_id) if job.task_id else None
        if task and (task.cancel_requested or task.payload.get("pause_requested")):
            job.status = "paused"
            task.status = "paused"
            await session.execute(update(Question).where(Question.id == task.question_id).values(status="paused"))
            await session.commit()
            return {"continue": False, "reason": "paused"}
        merged = dict(job.result_json or {})
        raw = payload.get("bundle")
        if raw:
            batch = CollectionBundleV2.model_validate(raw)
            if batch.question.id != job.request_json.get("question_external_id"):
                raise ValueError("批次问题与任务不一致")
            rows = {str(row["id"]): row for row in merged.get("answers", [])}
            for answer in batch.answers:
                row = answer.model_dump(mode="json")
                old = rows.get(answer.id)
                if old is None or len(row["content"]) >= len(old["content"]):
                    rows[answer.id] = row
            merged = {**batch.model_dump(mode="json"), "format": "CollectionBundleV3", "version": 3, "answers": list(rows.values())}
        elapsed = max(float(job.result_json.get("capture", {}).get("elapsed_seconds", 0)), min(1800, max(0, float(payload.get("elapsed_seconds", 0)))))
        reason = str(payload.get("stop_reason") or "")[:64]
        finished = bool(payload.get("finished")) or elapsed >= 1800
        if elapsed >= 1800:
            reason = "time_budget"
        count = len(merged.get("answers", []))
        if not job.request_json.get("read_all") and count >= job.max_answers:
            finished, reason = True, "answer_limit"
        if merged:
            capture = {**merged.get("capture", {}), "collected_answer_count": count,
                "visible_answer_count": max(count, int(merged.get("capture", {}).get("visible_answer_count", 0))),
                "elapsed_seconds": elapsed, "stop_reason": reason, "reached_end": reason == "page_end"}
            merged["capture"] = capture
            job.result_json = merged
            job.collected_answer_count = count
            job.capture_version = 3
            job.capture_method = "rendered_dom"
            job.capture_page_url = capture["page_url"]
            job.visible_answer_count = capture["visible_answer_count"]
            job.capture_diagnostics_json = capture.get("diagnostics", [])
            job.updated_at = utc_now()
        if finished and not count:
            job.status = "blocked"
            job.error_message = "没有完整的可用回答，请检查页面后继续"
            if task:
                task.status = "paused"
                task.error_message = job.error_message
                await session.execute(update(Question).where(Question.id == task.question_id).values(status="paused"))
        await session.commit()
        if not finished or not count:
            return {"continue": not finished, "saved": count, "reason": reason}
        # Validate the combined result before ending the job. It is not a single wire payload.
        merged = CollectionBundleV3.model_validate(merged).model_dump(mode="json")
    await complete_collection_job(factory, broker, client_id=client_id, job_id=job_id, nonce=nonce, bundle_payload=merged)
    return {"continue": False, "completed": True, "saved": count, "reason": reason}
