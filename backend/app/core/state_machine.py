from __future__ import annotations

from collections.abc import Mapping


class InvalidTaskTransition(ValueError):
    """任务状态变化不符合状态机。"""


TASK_TRANSITIONS: Mapping[str, set[str]] = {
    "queued": {"fetching_question", "cancelled", "failed"},
    "fetching_question": {
        "fetching_answers",
        "waiting_login",
        "waiting_verification",
        "cancelled",
        "failed",
    },
    "fetching_answers": {
        "cleaning_answers",
        "waiting_login",
        "waiting_verification",
        "cancelled",
        "failed",
    },
    "cleaning_answers": {"evaluating_answers", "cancelled", "failed"},
    "evaluating_answers": {"extracting_claims", "cancelled", "failed"},
    "extracting_claims": {"generating_embeddings", "cancelled", "failed"},
    "generating_embeddings": {"clustering_claims", "cancelled", "failed"},
    "clustering_claims": {"refining_clusters", "cancelled", "failed"},
    "refining_clusters": {"generating_opinion_map", "cancelled", "failed"},
    "generating_opinion_map": {"generating_article", "cancelled", "failed"},
    "generating_article": {"reviewing_article", "cancelled", "failed"},
    "reviewing_article": {"waiting_review", "cancelled", "failed"},
    "waiting_review": set(),
    "failed": {"queued"},
    "cancelled": {"queued"},
    "waiting_login": {"queued", "cancelled"},
    "waiting_verification": {"queued", "cancelled"},
}


def assert_task_transition(current: str, target: str) -> None:
    if target not in TASK_TRANSITIONS.get(current, set()):
        raise InvalidTaskTransition(f"不允许从 {current} 变更为 {target}")
