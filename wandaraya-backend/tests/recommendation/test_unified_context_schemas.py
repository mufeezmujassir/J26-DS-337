from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.recommendation.unified_context.schemas import (
    CONTEXT_DIMENSIONS,
    ContextEvidence,
    EvidenceStatus,
    RerankerConfiguration,
    SuppliedCandidate,
    UnifiedContextRequest,
)


def request(**overrides):
    values = {
        "query": "quiet heritage places",
        "travel_datetime": datetime(2027, 1, 2, 3, tzinfo=timezone.utc),
        "requested_activities": ["cultural sightseeing"],
        "activity_type_id": 2,
    }
    values.update(overrides)
    return UnifiedContextRequest(**values)


def test_context_contract_has_exactly_four_layers():
    assert CONTEXT_DIMENSIONS == ("weather", "time_of_day", "holiday_event", "historical_seasonality")
    assert "group_emotion" not in CONTEXT_DIMENSIONS


def test_request_normalizes_to_sri_lanka_timezone():
    assert request().travel_datetime.utcoffset().total_seconds() == 5.5 * 3600


def test_naive_time_is_rejected():
    with pytest.raises(ValidationError, match="explicit timezone"):
        request(travel_datetime=datetime(2027, 1, 2, 8))


def test_duplicate_supplied_candidates_are_rejected():
    supplied = [SuppliedCandidate(attraction_id=1, semantic_score=.5), SuppliedCandidate(attraction_id=1, semantic_score=.4)]
    with pytest.raises(ValidationError, match="must be unique"):
        request(candidates=supplied)


def test_limit_is_reduced_to_supplied_candidate_count():
    value = request(candidates=[SuppliedCandidate(attraction_id=1, semantic_score=.5)], limit=10)
    assert value.limit == 1


def test_candidate_pool_must_cover_limit():
    with pytest.raises(ValidationError, match="candidate_pool_size"):
        request(limit=10, candidate_pool_size=5)


@pytest.mark.parametrize("status", [
    EvidenceStatus.NOT_AVAILABLE, EvidenceStatus.NOT_APPLICABLE, EvidenceStatus.STALE,
    EvidenceStatus.ERROR, EvidenceStatus.UNSUPPORTED,
])
def test_unavailable_statuses_cannot_carry_scores(status):
    with pytest.raises(ValidationError, match="cannot carry a score"):
        ContextEvidence(
            dimension="weather", status=status, score=.5,
            evaluated_at=datetime.now(timezone.utc), travel_date=datetime.now().date(),
            explanation="not available",
        )


@pytest.mark.parametrize("configuration", list(RerankerConfiguration))
def test_all_supported_configurations_are_experimental_without_r4(configuration):
    assert configuration.value.startswith(("R0_", "R1_", "R2_", "R3_"))
    assert "GROUP" not in configuration.value


def test_group_emotion_input_is_rejected_by_contract():
    with pytest.raises(ValidationError):
        request(group_emotion={"score": .9})


def test_group_emotion_cannot_be_hidden_in_context_metadata():
    with pytest.raises(ValidationError, match="not supported"):
        request(contextual_metadata={"group_emotion": {"score": .9}})


def test_all_unified_flags_default_false():
    value = Settings(_env_file=None)
    assert value.ENABLE_UNIFIED_CONTEXT_ENGINE is False
    assert value.ENABLE_UNIFIED_CONTEXT_EXPERIMENTAL_RERANKING is False
    assert value.ENABLE_UNIFIED_CONTEXT_RESEARCH_API is False
    assert value.ENABLE_UNIFIED_CONTEXT_PRODUCTION_RANKING is False
