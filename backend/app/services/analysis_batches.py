"""Persist completed model batches before waiting on another model request."""
from backend.app.models.core import TaskLog


async def persist_analysis_batch(session, *, task, stage, completed, total,
                                 start_progress, end_progress):
    if task is not None:
        labels = {"evaluating_answers": "质量筛选", "extracting_claims": "观点提取",
                  "checking_survey_stances": "作者观点核对"}
        task.progress = max(task.progress, start_progress +
                            (end_progress - start_progress) * completed // max(1, total))
        session.add(TaskLog(task_id=task.id, stage=stage,
            message=f"{labels[stage]}：已保存 {completed}/{total} 条回答的分析结果",
            metadata_json={"completed": completed, "total": total}))
    # Include validated responses, usage and analysis in the same durable batch.
    # In particular, do not hold SQLite's write lock while awaiting the next call.
    await session.commit()
