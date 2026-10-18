from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.knowledge_base.retrieval.semantic_retriever import SemanticCandidate
from app.recommendation.content_based.schemas import ContentBasedRecommendationRequest
from app.recommendation.content_based.service import (
    ContentBasedRecommendationService,
    HydratedAttraction,
)


class FakeRetriever:
    def __init__(self, candidates):
        self.search = AsyncMock(return_value=candidates)


def record(attraction_id, *, name=None, district_id=78, categories=("Heritage",), activities=("Hiking",), price_level=2, region_name=None):
    attraction = type(
        "AttractionRow",
        (),
        {
            "id": attraction_id,
            "name": name or f"Attraction {attraction_id}",
            "district_id": district_id,
            "price_level": price_level,
        },
    )()
    return HydratedAttraction(attraction, tuple(categories), tuple(activities), region_name)


def request(**kwargs):
    return ContentBasedRecommendationRequest(interests="heritage hiking", **kwargs)


def candidate(attraction_id, score=0.8):
    return SemanticCandidate(attraction_id, f"Attraction {attraction_id}", score, "Galle", 78)


def test_category_activity_district_evidence_and_stable_tie_breaking():
    service = ContentBasedRecommendationService(None, FakeRetriever([]))
    payload = request(
        preferred_categories=["heritage"],
        preferred_activities=["hiking"],
        preferred_district_ids=[78],
    )
    response = service.rank_hydrated(
        payload,
        "heritage hiking",
        [candidate(2, 0.8), candidate(1, 0.8)],
        {1: record(1), 2: record(2)},
    )
    assert [item.attraction_id for item in response.recommendations] == [1, 2]
    assert response.recommendations[0].category_match_score == 1
    assert response.recommendations[0].activity_match_score == 1
    assert response.recommendations[0].district_match_score == 1
    assert response.recommendations[0].semantic_relevance_score == 0.9


def test_missing_soft_metadata_is_unavailable_not_zero():
    service = ContentBasedRecommendationService(None, FakeRetriever([]))
    response = service.rank_hydrated(
        request(preferred_categories=["heritage"], preferred_activities=["hiking"]),
        "heritage hiking",
        [candidate(1)],
        {1: record(1, categories=(), activities=())},
    )
    item = response.recommendations[0]
    assert item.category_match_score is None
    assert item.activity_match_score is None
    assert set(item.matched_preference_evidence["unavailable_dimensions"]) >= {"category", "activity"}


def test_hard_filters_conservatively_exclude_missing_or_nonmatching_metadata():
    service = ContentBasedRecommendationService(None, FakeRetriever([]))
    response = service.rank_hydrated(
        request(hard_filters={"category_names": ["heritage"], "max_price_level": 2}),
        "heritage hiking",
        [candidate(1), candidate(2)],
        {
            1: record(1, categories=()),
            2: record(2, categories=("Heritage",), price_level=None),
        },
    )
    assert response.recommendations == []
    assert response.excluded_candidate_counts == {
        "hard_budget_metadata_missing": 1,
        "hard_category_metadata_missing": 1,
    }


def test_duplicate_and_inactive_or_missing_hydrated_candidates_are_excluded():
    service = ContentBasedRecommendationService(None, FakeRetriever([]))
    candidates = service._deduplicate_candidates([candidate(1, 0.6), candidate(1, 0.9), candidate(2)])
    assert [(item.attraction_id, item.score) for item in candidates] == [(1, 0.9), (2, 0.8)]
    response = service.rank_hydrated(request(), "heritage", candidates, {1: record(1)})
    assert [item.attraction_id for item in response.recommendations] == [1]
    assert response.excluded_candidate_counts["inactive_or_unavailable_postgresql_record"] == 1


def test_empty_preferences_only_use_semantic_component():
    service = ContentBasedRecommendationService(None, FakeRetriever([]))
    response = service.rank_hydrated(request(), "heritage", [candidate(1, 0.4)], {1: record(1)})
    item = response.recommendations[0]
    assert item.baseline_score == item.semantic_relevance_score == 0.7
    assert item.category_match_score is None


def test_complete_preference_phrase_matches_verified_more_specific_category_label():
    service = ContentBasedRecommendationService(None, FakeRetriever([]))
    response = service.rank_hydrated(
        request(preferred_categories=["Heritage"], hard_filters={"category_names": ["Heritage"]}),
        "heritage", [candidate(1)], {1: record(1, categories=("Culture & Heritage",))},
    )
    assert response.recommendations[0].category_match_score == 1
    assert response.recommendations[0].matched_preference_evidence["matched_categories"] == ["Culture & Heritage"]


def test_region_preferences_use_verified_province_and_share_geographic_weight():
    service = ContentBasedRecommendationService(None, FakeRetriever([]))
    response = service.rank_hydrated(
        request(preferred_regions=["Southern Province"]),
        "heritage", [candidate(1)], {1: record(1, region_name="Southern Province")},
    )
    assert response.recommendations[0].region_match_score == 1
    assert response.recommendations[0].district_match_score is None


def test_invalid_limits_and_weights_are_rejected():
    with pytest.raises(ValidationError):
        ContentBasedRecommendationRequest(interests="x", limit=0)
    with pytest.raises(ValidationError):
        ContentBasedRecommendationRequest(interests="heritage", candidate_pool_size=2, limit=3)
    with pytest.raises(ValidationError):
        ContentBasedRecommendationRequest(interests="heritage", weights={"semantic": 0, "category": 1})


@pytest.mark.asyncio
async def test_retrieval_and_hydration_errors_propagate_without_writes():
    retriever = FakeRetriever([])
    retriever.search.side_effect = RuntimeError("Qdrant unavailable")
    service = ContentBasedRecommendationService(object(), retriever)
    with pytest.raises(RuntimeError, match="Qdrant unavailable"):
        await service.recommend(request())

    service = ContentBasedRecommendationService(object(), FakeRetriever([candidate(1)]))
    service._hydrate = AsyncMock(side_effect=RuntimeError("PostgreSQL unavailable"))
    with pytest.raises(RuntimeError, match="PostgreSQL unavailable"):
        await service.recommend(request())
