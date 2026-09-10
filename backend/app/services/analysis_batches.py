"""Persist completed model batches before waiting on another model request."""
from backend.app.models.core import TaskLog
from backend.app.services.checkpoints import PipelinePaused


async def persist_analysis_batch(session, *, task, stage, completed, total,
                                 start_progress, end_progress, unit="条回答"):
    if task is not None:
        labels = {"evaluating_answers": "质量筛选", "extracting_claims": "观点提取",
                  "checking_survey_stances": "作者观点核对", "refining_clusters": "观点归并",
                  "merging_cluster_batches": "跨批观点归并"}
        task.progress = max(task.progress, start_progress +
                            (end_progress - start_progress) * completed // max(1, total))
        session.add(TaskLog(task_id=task.id, stage=stage,
            message=f"{labels[stage]}：已保存 {completed}/{total} {unit}的分析结果",
            metadata_json={"completed": completed, "total": total}))
    # Include validated responses, usage and analysis in the same durable batch.
    # In particular, do not hold SQLite's write lock while awaiting the next call.
    await session.commit()
    if task is not None:
        await session.refresh(task, ["payload"])
        if (task.payload or {}).get("pause_requested"):
            raise PipelinePaused("已保存当前批次并暂停；点击继续可复用已保存结果")
