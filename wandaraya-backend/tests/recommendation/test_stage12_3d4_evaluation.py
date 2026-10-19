from app.recommendation.evaluation.holiday_event_stage12_3d4 import (
    candidate_weight_grid,
    combined_score,
    deterministic_split,
    ranking_metrics,
    validate_human_annotations,
    weighted_kappa,
)


def test_annotation_validation_rejects_unknown_duplicate_and_missing_rows():
    outcome = validate_human_annotations(
        [
            {"reviewer_id": "R1", "query_id": "q", "attraction_id": "1", "relevance_0_to_3": "3"},
            {"reviewer_id": "R1", "query_id": "q", "attraction_id": "1", "relevance_0_to_3": "3"},
            {"reviewer_id": "R2", "query_id": "q", "attraction_id": "2", "relevance_0_to_3": ""},
            {"reviewer_id": "R2", "query_id": "bad", "attraction_id": "3", "relevance_0_to_3": "1"},
        ],
        {("q", "1"), ("q", "2")},
    )
    assert len(outcome["valid"]) == 1
    assert len(outcome["duplicates"]) == 1
    assert len(outcome["missing"]) == 1
    assert len(outcome["invalid"]) == 1


def test_cannot_judge_is_not_silently_treated_as_irrelevant():
    outcome = validate_human_annotations(
        [{"reviewer_id": "R1", "query_id": "q", "attraction_id": "1", "cannot_judge": "true", "relevance_0_to_3": ""}],
        {("q", "1")},
    )
    assert outcome["valid"][0]["cannot_judge"] is True
    assert outcome["valid"][0]["relevance_0_to_3"] is None


def test_split_is_deterministic_and_group_safe():
    specs = [{"query_id": "one", "scenario_group": "same"}, {"query_id": "two", "scenario_group": "same"}, {"query_id": "three", "scenario_group": "other"}]
    first = deterministic_split(specs, seed=7)
    assert first == deterministic_split(specs, seed=7)
    assert first["one"] == first["two"]


def test_missing_context_retains_baseline_and_metrics_report_unjudged():
    assert combined_score(.72, None) == .72
    metrics = ranking_metrics(["1", "2"], {"1": 3}, 5)
    assert metrics["unjudged_candidates_in_ranked_list"] == 1
    assert metrics["precision_at_5"] == 1.0


def test_weight_grid_is_nonnegative_and_sums_to_one():
    grid = candidate_weight_grid(.5)
    assert grid
    assert all(all(value >= 0 for value in item.values()) and sum(item.values()) == 1 for item in grid)


def test_weighted_kappa_requires_two_comparable_reviewers_and_is_perfect_when_equal():
    rows = [
        {"reviewer_id": "R1", "query_id": "q", "attraction_id": "1", "cannot_judge": False, "relevance_0_to_3": 3},
        {"reviewer_id": "R2", "query_id": "q", "attraction_id": "1", "cannot_judge": False, "relevance_0_to_3": 3},
        {"reviewer_id": "R1", "query_id": "q", "attraction_id": "2", "cannot_judge": False, "relevance_0_to_3": 1},
        {"reviewer_id": "R2", "query_id": "q", "attraction_id": "2", "cannot_judge": False, "relevance_0_to_3": 1},
    ]
    assert weighted_kappa(rows, "R1", "R2") == 1.0
