from scripts.enrich_srilanka_tourism_gate5e2c2 import category_candidate, physical_attraction_candidate, valid_coordinate
from scripts.prepare_srilanka_tourism_district_lookup_queue import build_queue


def test_coordinate_validation_rejects_missing_and_outside_sri_lanka():
    assert valid_coordinate({}) == (None, None)
    assert valid_coordinate({"latitude": 51.5, "longitude": -0.1}) == (None, None)
    assert valid_coordinate({"latitude": 6.9, "longitude": 79.9}) == (6.9, 79.9)


def test_category_requires_an_existing_taxonomy_mapping():
    assert category_candidate(official_name="Unknown place", google_types=[], categories={})[0] is None
    assert category_candidate(official_name="Ancient Fortress", google_types=[], categories={"History & Archaeology": 7}) == (
        "History & Archaeology", 7, "official_title_historical_term",
    )


def test_category_mapping_uses_specific_google_type_before_generic_title():
    result = category_candidate(official_name="Koggala Beach", google_types=["beach", "natural_feature"], categories={"Beaches & Coastal": 36, "Nature & Landscapes": 35})
    assert result == ("Beaches & Coastal", 36, "stored_google_beach_type")


def test_saved_google_display_name_can_confirm_a_generic_waterfall_category():
    result = category_candidate(official_name="Asupini Ella", google_name="Asupini Ella Falls", google_types=["tourist_attraction"], categories={"Nature & Landscapes": 35})
    assert result == ("Nature & Landscapes", 35, "official_title_natural_feature_term")


def test_locality_only_google_candidate_cannot_supply_attraction_identity():
    assert not physical_attraction_candidate(["locality", "political"])
    assert physical_attraction_candidate(["tourist_attraction", "point_of_interest"])
    assert physical_attraction_candidate(["lake", "natural_feature"])


def test_district_queue_only_selects_unresolved_records_once():
    source = {"source_attraction_id": "official:1", "official_name": "A", "official_source_url": "https://example.test/a", "conflicts": ["missing_verified_district"]}
    assert len(build_queue([source, source, {**source, "source_attraction_id": "official:2", "conflicts": []}])) == 1
