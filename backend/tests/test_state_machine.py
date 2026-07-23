import pytest

from backend.app.core.state_machine import (
    InvalidTaskTransition,
    assert_task_transition,
)


def test_valid_task_transitions() -> None:
    assert_task_transition("queued", "fetching_question")
    assert_task_transition("fetching_question", "fetching_answers")
    assert_task_transition("fetching_answers", "cleaning_answers")
    assert_task_transition("cleaning_answers", "evaluating_answers")
    assert_task_transition("evaluating_answers", "extracting_claims")
    assert_task_transition("extracting_claims", "generating_embeddings")
    assert_task_transition("generating_embeddings", "clustering_claims")
    assert_task_transition("clustering_claims", "refining_clusters")
    assert_task_transition("refining_clusters", "generating_opinion_map")
    assert_task_transition("generating_opinion_map", "generating_article")
    assert_task_transition("generating_article", "reviewing_article")
    assert_task_transition("reviewing_article", "waiting_review")
    assert_task_transition("failed", "queued")


def test_invalid_task_transition_is_rejected() -> None:
    with pytest.raises(InvalidTaskTransition):
        assert_task_transition("waiting_review", "queued")
