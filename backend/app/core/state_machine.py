from __future__ import annotations

from collections.abc import Mapping


class InvalidTaskTransition(ValueError):
    """任务状态变化不符合状态机。"""


TASK_TRANSITIONS: Mapping[str, set[str]] = {
    "queued": {"extracting_claims", "cancelled", "failed"},
    "extracting_claims": {"waiting_review", "cancelled", "failed"},
    "waiting_review": set(),
    "failed": {"queued"},
    "cancelled": {"queued"},
}


def assert_task_transition(current: str, target: str) -> None:
    if target not in TASK_TRANSITIONS.get(current, set()):
        raise InvalidTaskTransition(f"不允许从 {current} 变更为 {target}")

