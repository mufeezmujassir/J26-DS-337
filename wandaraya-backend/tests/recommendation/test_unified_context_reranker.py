from datetime import date, datetime, timezone
from itertools import product

import pytest

from app.recommendation.unified_context.reranker import ExperimentalContextReranker, RankingCandidate
from app.recommendation.unified_context.schemas import ContextEvidence, EvidenceStatus, RerankerConfiguration


def evidence(dimension, score=None, confidence=.8, status=EvidenceStatus.AVAILABLE, **details):
    return ContextEvidence(
        dimension=dimension, status=status, score=score, confidence=confidence,
        source=f"test:{dimension}", source_version="fixture_v1",
        evaluated_at=datetime.now(timezone.utc), travel_date=date(2027, 1, 1),
        explanation=f"Evidence for {dimension}", details=details,
    )


def candidate(identifier, semantic, rank, scores=None):
    scores = scores or {}
    dimensions = ("weather", "time_of_day", "holiday_event", "historical_seasonality")
    bundle = {
        dimension: evidence(
            dimension,
            scores.get(dimension),
            status=EvidenceStatus.AVAILABLE if dimension in scores else EvidenceStatus.NOT_AVAILABLE,
            confidence=.8 if dimension in scores else None,
        ) for dimension in dimensions
    }
    return RankingCandidate(identifier, f"A{identifier}", semantic * 2 - 1, semantic, rank, bundle, {})


@pytest.mark.parametrize("semantic", [index / 40 for index in range(41)])
def test_r0_preserves_semantic_score_across_bounds(semantic):
    result = ExperimentalContextReranker().rerank(
        [candidate(1, semantic, 1, {"weather": 1 - semantic})], RerankerConfiguration.R0, .65
    )[0]
    assert result.final_experimental_context_score == pytest.approx(semantic)
    assert result.context_score is None
    assert result.contributions == []


@pytest.mark.parametrize("weather,seasonality", list(product([0, .25, .5, 1], repeat=2)))
def test_r3_combines_weather_and_seasonality_as_one_climate_dimension(weather, seasonality):
    item = candidate(1, .5, 1, {"weather": weather, "historical_seasonality": seasonality})
    result = ExperimentalContextReranker().rerank([item], RerankerConfiguration.R3, .65)[0]
    assert result.context_score == pytest.approx((weather + seasonality) / 2)
    assert len(result.contributions) == 1
    assert result.contributions[0].dimension == "weather_seasonality_combined"


@pytest.mark.parametrize("missing_dimension", ["weather", "time_of_day", "holiday_event", "historical_seasonality"])
def test_missing_dimension_is_not_replaced_with_zero(missing_dimension):
    scores = {name: .8 for name in ("weather", "time_of_day", "holiday_event", "historical_seasonality") if name != missing_dimension}
    result = ExperimentalContextReranker().rerank([candidate(1, .5, 1, scores)], RerankerConfiguration.R1, .5)[0]
    assert result.context_score == .8
    assert missing_dimension in result.explanation.missing_dimensions


def test_no_context_falls_back_to_semantic_without_penalty():
    result = ExperimentalContextReranker().rerank([candidate(1, .72, 1)], RerankerConfiguration.R2, .65)[0]
    assert result.final_experimental_context_score == .72
    assert result.context_score is None


def test_stable_tie_break_preserves_semantic_rank():
    results = ExperimentalContextReranker().rerank(
        [candidate(2, .5, 1), candidate(1, .5, 2)], RerankerConfiguration.R0, .65
    )
    assert [item.attraction_id for item in results] == [2, 1]


def test_attraction_id_is_final_deterministic_tie_break():
    first = candidate(2, .5, 1)
    second = candidate(1, .5, 1)
    results = ExperimentalContextReranker().rerank([first, second], RerankerConfiguration.R0, .65)
    assert [item.attraction_id for item in results] == [1, 2]


def test_known_closure_cannot_be_bypassed_by_positive_context():
    item = candidate(1, 1, 1, {"weather": 1, "time_of_day": 0, "holiday_event": 1, "historical_seasonality": 1})
    item.evidence["time_of_day"].details["opening_status"] = "CLOSED"
    result = ExperimentalContextReranker().rerank([item], RerankerConfiguration.R1, .65)[0]
    assert result.final_experimental_context_score == 0


def test_r0_remains_a_pure_semantic_baseline_even_when_context_exists():
    item = candidate(1, .8, 1, {"time_of_day": 0})
    item.evidence["time_of_day"].details["opening_status"] = "CLOSED"
    result = ExperimentalContextReranker().rerank([item], RerankerConfiguration.R0, .65)[0]
    assert result.final_experimental_context_score == .8


def test_rank_movement_is_reported():
    results = ExperimentalContextReranker().rerank([
        candidate(1, .9, 1, {"weather": 0}),
        candidate(2, .8, 2, {"weather": 1}),
    ], RerankerConfiguration.R1, .2)
    by_id = {item.attraction_id: item for item in results}
    assert by_id[2].rank_movement == 1
    assert by_id[1].rank_movement == -1


def test_r2_uses_evidence_quality_as_a_transparent_weight():
    item = candidate(1, .5, 1, {"weather": 1, "time_of_day": 0})
    item.evidence["weather"].confidence = .9
    item.evidence["time_of_day"].confidence = .1
    result = ExperimentalContextReranker().rerank([item], RerankerConfiguration.R2, .5)[0]
    assert result.context_score == .9


def test_r2_excludes_available_evidence_without_quality_instead_of_inventing_it():
    item = candidate(1, .5, 1, {"weather": 1, "time_of_day": 0})
    item.evidence["weather"].confidence = None
    result = ExperimentalContextReranker().rerank([item], RerankerConfiguration.R2, .5)[0]
    assert result.context_score == 0
    assert [part.dimension for part in result.contributions] == ["time_of_day"]


@pytest.mark.parametrize("configuration", list(RerankerConfiguration))
def test_repeated_execution_is_deterministic(configuration):
    values = [candidate(1, .7, 1, {"weather": .4}), candidate(2, .6, 2, {"weather": .9})]
    reranker = ExperimentalContextReranker()
    first = reranker.rerank(values, configuration, .65)
    second = reranker.rerank(values, configuration, .65)
    assert [(x.attraction_id, x.final_experimental_context_score) for x in first] == [
        (x.attraction_id, x.final_experimental_context_score) for x in second
    ]


@pytest.mark.parametrize("score", [0, .2, .39, .4, .59, .6, .8, 1])
def test_explanations_only_classify_supported_scores(score):
    result = ExperimentalContextReranker().rerank(
        [candidate(1, .5, 1, {"weather": score})], RerankerConfiguration.R1, .5
    )[0]
    if score >= .6:
        assert result.explanation.positive_factors
    elif score < .4:
        assert result.explanation.negative_factors
    else:
        assert not result.explanation.positive_factors
        assert not result.explanation.negative_factors
