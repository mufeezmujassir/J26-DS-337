from app.recommendation.content_based.experimental_policy import experimental_order
from app.recommendation.content_based.service import HydratedAttraction
from app.recommendation.content_based.schemas import ContentBasedRecommendationItem


def item(attraction_id, score, category=1.0, activity=1.0, district=1.0):
    return ContentBasedRecommendationItem(attraction_id=attraction_id, attraction_name=str(attraction_id), district_id=78, baseline_score=score, semantic_relevance_score=score, raw_semantic_similarity=score * 2 - 1, category_match_score=category, activity_match_score=activity, district_match_score=district, ranking_explanation="test")


def record(attraction_id, name="Attraction", categories=("Heritage",), activities=("Walking",)):
    attraction = type("Attraction", (), {"id": attraction_id, "name": name, "district_id": 78})()
    return HydratedAttraction(attraction, categories, activities)


def test_review_flagged_junction_is_after_verified_preference_evidence_without_score_mutation():
    good, junction = item(1, 0.7), item(2, 0.9)
    result = experimental_order([junction, good], {1: record(1), 2: record(2, name="Town Junction")})
    assert [row["item"].attraction_id for row in result] == [1, 2]
    assert result[1]["item"].baseline_score == 0.9


def test_missing_metadata_is_not_marked_as_negative_match():
    unknown = item(1, 0.8, category=None, activity=None)
    result = experimental_order([unknown], {1: record(1, categories=(), activities=())})[0]
    assert result["eligibility_bucket"] == 1
    assert unknown.category_match_score is None
