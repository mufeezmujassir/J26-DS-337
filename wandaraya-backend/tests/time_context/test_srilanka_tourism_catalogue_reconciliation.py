from app.time_context.governance.catalogue_reconciliation import ExistingAttraction, reconcile_record, reconcile_registry, validate_catalogue_registry


def _kb(id=1, name="Galle Fort", district="Galle", latitude=None, longitude=None, aliases=(), source_urls=(), google_place_id=None):
    return ExistingAttraction(id=id, name=name, slug=name.casefold().replace(" ", "-"), google_place_id=google_place_id,
        district_id=id, district_name=district, city=district, latitude=latitude, longitude=longitude,
        categories=(), aliases=(name, *aliases), external_source_urls=source_urls)


def _record(name="Galle Fort", **extra):
    return {"external_source_id": "srilanka_tourism_attraction:153", "preferred_attraction_name": name,
            "canonical_source_url": "https://srilanka.travel/attraction?attraction_id=153", "provenance": [], **extra}


def test_exact_name_and_alias_are_existing_matches():
    exact = reconcile_record(_record(), [_kb()])
    assert exact["classification"] == "existing_kb_match"
    alias = reconcile_record(_record("Dutch Fort"), [_kb(aliases=("Dutch Fort",))])
    assert alias["classification"] == "existing_kb_match"
    assert alias["match_evidence"][0]["method"] == "exact_alias"


def test_external_source_and_google_id_take_priority():
    source = reconcile_record(_record(), [_kb(source_urls=("https://srilanka.travel/attraction?attraction_id=153",))])
    assert source["match_evidence"][0]["method"] == "exact_source_url"
    google = reconcile_record(_record("Unrelated", google_place_id="place-1"), [_kb(google_place_id="place-1")])
    assert google["match_evidence"][0]["method"] == "exact_google_place_id"


def test_ambiguous_fuzzy_and_missing_records_are_not_auto_merged():
    ambiguous = reconcile_record(_record("Ella"), [_kb(1, "Ella", "Badulla"), _kb(2, "Ella", "Matara")])
    assert ambiguous["classification"] == "ambiguous_multiple_matches"
    fuzzy = reconcile_record(_record("Galle Forte"), [_kb()])
    assert fuzzy["classification"] == "probable_match_review_required"
    missing = reconcile_record(_record("", external_source_id="x"), [_kb()])
    assert missing["classification"] == "insufficient_evidence"


def test_geographic_match_is_review_only_and_registry_prevents_duplicate_ids():
    geographic = reconcile_record(_record("Different", latitude=6.03, longitude=80.21), [_kb(latitude=6.0302, longitude=80.2102)])
    assert geographic["classification"] == "probable_match_review_required"
    records = [_record(), _record(raw_source_names=["duplicate"])]
    result = reconcile_registry(registry={"records": records}, existing=[_kb()])
    assert len(result) == 1
    validation = validate_catalogue_registry({"records": records})
    assert validation["duplicate_external_source_ids"] == ["srilanka_tourism_attraction:153"]
