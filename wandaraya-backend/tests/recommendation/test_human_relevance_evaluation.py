from app.recommendation.evaluation.human_relevance import disagreement_report, ranking_metrics, validate_annotations


def test_validation_detects_missing_duplicate_and_invalid_labels():
    outcome = validate_annotations([
        {"reviewer_id": "R1", "query_id": "q", "attraction_id": "1", "relevance_0_to_3": "3"},
        {"reviewer_id": "R1", "query_id": "q", "attraction_id": "1", "relevance_0_to_3": "2"},
        {"reviewer_id": "R2", "query_id": "q", "attraction_id": "2", "relevance_0_to_3": ""},
        {"reviewer_id": "R2", "query_id": "q", "attraction_id": "3", "relevance_0_to_3": "4"},
    ])
    assert len(outcome["valid"]) == 1 and len(outcome["duplicates"]) == 1
    assert len(outcome["missing"]) == 1 and len(outcome["invalid"]) == 1


def test_disagreement_is_reported_without_automatic_adjudication():
    report = disagreement_report([
        {"reviewer_id": "R1", "query_id": "q", "attraction_id": "1", "relevance_0_to_3": 3},
        {"reviewer_id": "R2", "query_id": "q", "attraction_id": "1", "relevance_0_to_3": 1},
    ])
    assert report[0]["requires_adjudication"] is True


def test_identical_scores_are_not_listed_as_disagreements():
    assert disagreement_report([
        {"reviewer_id": "R1", "query_id": "q", "attraction_id": "1", "relevance_0_to_3": 2},
        {"reviewer_id": "R2", "query_id": "q", "attraction_id": "1", "relevance_0_to_3": 2},
    ]) == []


def test_precision_recall_and_ndcg_use_judged_pool_denominator():
    values = ranking_metrics(["1", "2", "3"], {"1": 3, "2": 0, "3": 2}, 2)
    assert values["precision_at_2"] == 0.5
    assert values["judged_pool_recall_at_2"] == 0.5
    assert 0 < values["ndcg_at_2"] <= 1


def test_empty_judged_pool_does_not_claim_metrics():
    values = ranking_metrics(["1"], {}, 5)
    assert values["precision_at_5"] is None and values["judged_pool_recall_at_5"] is None


def test_mrr_respects_the_requested_cutoff():
    values = ranking_metrics(["1", "2", "3"], {"1": 0, "2": 0, "3": 3}, 2)
    assert values["mrr_at_2"] is None
