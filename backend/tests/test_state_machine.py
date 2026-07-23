import pytest

from backend.app.core.state_machine import (
    InvalidTaskTransition,
    assert_task_transition,
)


def test_valid_task_transitions() -> None:
    assert_task_transition("queued", "extracting_claims")
    assert_task_transition("extracting_claims", "waiting_review")
    assert_task_transition("failed", "queued")


def test_invalid_task_transition_is_rejected() -> None:
    with pytest.raises(InvalidTaskTransition):
        assert_task_transition("waiting_review", "queued")

