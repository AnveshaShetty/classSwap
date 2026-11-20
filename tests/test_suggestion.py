import pytest

from app.services.suggestion import (
    CandidateFeatures,
    adjacent_free_score,
    calculate_score,
    fairness_score,
    rank_candidates,
    subject_match_score,
)


def test_adjacent_free_score_for_busy_and_free_neighbors() -> None:
    assert adjacent_free_score(3, 7, {2, 4}, ()) == 0.0
    assert adjacent_free_score(3, 7, set(), ()) == 1.0


def test_first_period_missing_neighbor_counts_as_free() -> None:
    assert adjacent_free_score(1, 7, set(), ()) == 1.0
    assert adjacent_free_score(1, 7, {2}, ()) == 0.5


def test_break_separates_adjacent_periods() -> None:
    assert adjacent_free_score(3, 7, {2}, (2, 4)) == 1.0
    assert adjacent_free_score(2, 7, {3}, (2, 4)) == 1.0


def test_fairness_and_subject_match_scores() -> None:
    assert fairness_score(0, 0) == 1.0
    assert fairness_score(2, 4) == 0.5
    assert subject_match_score(True, True) == 1.0
    assert subject_match_score(False, True) == 0.5
    assert subject_match_score(False, False) == 0.0


def test_free_neighbors_break_tie_between_subject_matches() -> None:
    busy = CandidateFeatures(1, "Busy", "busy@demo.edu", 1.0, 0.0, 1.0, 1.0, 1.0, 0)
    free = CandidateFeatures(2, "Free", "free@demo.edu", 1.0, 1.0, 1.0, 1.0, 1.0, 0)

    ranked = rank_candidates([busy, free])

    assert ranked[0].email == "free@demo.edu"
    assert ranked[0].score > ranked[1].score
    assert "no back-to-back load" in ranked[0].reason


def test_score_rejects_out_of_range_features() -> None:
    invalid = CandidateFeatures(1, "Invalid", "invalid@demo.edu", 1.1, 1.0, 1.0, 1.0, 1.0, 0)
    with pytest.raises(ValueError, match="between 0 and 1"):
        calculate_score(invalid)
