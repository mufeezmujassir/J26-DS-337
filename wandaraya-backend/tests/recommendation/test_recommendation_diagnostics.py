from app.recommendation.content_based.diagnostics import eligibility_review_flags, requested_metadata_coverage
from app.recommendation.content_based.service import HydratedAttraction


def record(name="Galle Fort", district_id=78, categories=("Heritage",), activities=("Walking",)):
    row = type("Attraction", (), {"name": name, "district_id": district_id})()
    return HydratedAttraction(row, categories, activities)


def test_junction_is_queued_for_review_not_automatically_excluded():
    flags = eligibility_review_flags(record(name="Jayanthi Junction"))
    assert "name_requires_tourism_eligibility_review" in flags


def test_missing_metadata_is_reported_without_being_treated_as_negative_match():
    flags = eligibility_review_flags(record(categories=(), activities=()))
    assert {"missing_category_metadata", "missing_activity_metadata"}.issubset(flags)


def test_requested_metadata_coverage_is_deterministic():
    assert requested_metadata_coverage(record(categories=(), activities=("Walking",)), wants_category=True, wants_activity=True, wants_district=True) == 2 / 3
