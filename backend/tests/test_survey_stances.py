import pytest

from backend.app.services.survey_stances import SurveyStanceMatrix, validate_matrix


def matrix(relations, evidence, answer_id="a"):
    return SurveyStanceMatrix.model_validate({"answers": [{"answer_id": answer_id,
        "relations": relations, "evidence": evidence}]})


def test_checks_multiple_directions_with_verbatim_evidence():
    result = validate_matrix(matrix(["supports", "conditional", "not_mentioned"],
        ["需求前置", "如果条件满足，出海可增长", ""]),
        [{"id": "a", "content": "补贴导致需求前置。如果条件满足，出海可增长。"}], ["x", "y", "z"])
    assert result["a"]["x"]["relation"] == "supports"
    assert result["a"]["y"]["quote"] == "如果条件满足，出海可增长"


@pytest.mark.parametrize("value", [
    matrix(["supports"], ["需求前置"]),
    matrix(["supports", "not_mentioned"], ["编造的引文", ""]),
    matrix(["supports", "not_mentioned"], ["需求前置", "需求前置"]),
    matrix(["supports", "not_mentioned"], ["需求前置", ""], "unknown"),
])
def test_rejects_incomplete_or_unverifiable_matrix(value):
    with pytest.raises(ValueError):
        validate_matrix(value, [{"id": "a", "content": "需求前置"}], ["x", "y"])


def test_rejects_duplicate_answers():
    item = {"answer_id": "a", "relations": ["supports"], "evidence": ["需求前置"]}
    with pytest.raises(ValueError):
        validate_matrix(SurveyStanceMatrix.model_validate({"answers": [item, item]}),
            [{"id": "a", "content": "需求前置"}], ["x"])
