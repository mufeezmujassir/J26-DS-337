from datetime import datetime, timezone

from app.time_context.governance.catalogue_discovery import (
    CatalogueBatchPlan,
    CatalogueApprovedUrl,
    build_catalogue_seed_manifest,
    build_full_discovery_manifest,
    build_registry,
    extract_catalogue_page,
    parse_researcher_approval_timestamp,
    validate_approval_reference,
    write_next_batch_plan,
    write_catalogue_reports,
)


def test_paginated_listing_extracts_cards_filters_and_excludes_navigation():
    page = extract_catalogue_page(
        source_url="https://www.srilanka.travel/attractions",
        html=b'''<nav><a href="/attraction?attraction_id=163">Navigation Yala</a></nav>
        <div class="attractions-results-head"><span class="attractions-count">12 shown</span></div>
        <div class="attractions-grid"><article class="attraction-card"><div class="attraction-card-body"><h3>Yala National Park</h3><p>Official card description.</p><a href="/attraction&attraction_id=163">View Details</a></div></article></div>
        <div class="attractions-pagination"><a href="/tourist-attractions?page=2">2</a><div class="results">Showing 1 to 12 of 169 (15 Pages)</div></div>
        <ul class="attractions-tabs"><li><a href="/index.php?route=attractions/attractions-search&theme=2">Wild</a></li></ul>''',
        retrieved_at=datetime.now(timezone.utc),
    )
    assert len(page.cards) == 1
    assert page.cards[0].external_source_id == "srilanka_tourism_attraction:163"
    assert page.cards[0].listing_description == "Official card description."
    assert page.cards[0].raw_source_name == "Yala National Park"
    assert page.pagination_urls == ["https://srilanka.travel/tourist-attractions?page=2"]
    assert len(page.theme_search_urls) == 1
    assert page.total_attraction_count == 169 and page.total_page_count == 15


def test_theme_page_deduplicates_detail_references_and_retains_theme_id():
    page = extract_catalogue_page(
        source_url="https://srilanka.travel/index.php?route=attractions%2Fattractions-search&theme=2",
        html=b'''<ul class="attractions-tabs"><li><a href="/index.php?route=attractions/attractions-search&theme=2">Heritage</a></li></ul><div class="attractions-grid"><article class="attraction-card"><h3>Sigiriya</h3><a href="/attraction&attraction_id=160">View</a></article>
        <article class="attraction-card"><h3>Sigiriya duplicate</h3><a href="/attraction&attraction_id=160">View</a></article></div>''',
    )
    assert len(page.cards) == 1 and page.duplicate_card_references == 1
    assert page.cards[0].observed_theme_ids == ["2"]
    assert page.cards[0].observed_theme_names == ["Heritage"]


def test_registry_merges_verified_ids_and_preserves_google_places_unknowns(tmp_path):
    one = extract_catalogue_page(source_url="https://srilanka.travel/attractions", html=b"<div class='attractions-grid'><article class='attraction-card'><h3>Sigiriya</h3><a href='/attraction&attraction_id=160'>View</a></article></div>")
    two = extract_catalogue_page(source_url="https://srilanka.travel/tourist-attractions?page=2", html=b"<div class='attractions-grid'><article class='attraction-card'><h3>Sigiriya</h3><a href='/attraction&attraction_id=160'>View</a></article></div>")
    registry, unresolved = build_registry(pages=[one, two])
    assert len(registry) == 1 and not unresolved
    assert registry[0]["google_place_id"] is None
    assert registry[0]["reconciliation_status"] == "pending_gate_5c_read_only_reconciliation"
    reports = write_catalogue_reports(pages=[one, two], reports_dir=tmp_path, batch_id="offline_catalogue")
    assert reports["attraction_registry"].exists()


def test_catalogue_plan_requires_explicit_approved_known_urls_and_timestamp():
    seeds = {item["canonical_url"] for item in build_catalogue_seed_manifest()["known_distinct_url_structures"]}
    plan = CatalogueBatchPlan(approved_urls=[CatalogueApprovedUrl(canonical_url="https://srilanka.travel/attractions")])
    assert "separate_execution_approval_missing" in plan.readiness_errors(seeds)
    assert any(item.startswith("url_not_explicitly_approved") for item in plan.readiness_errors(seeds))


def test_complete_batch_plan_requires_matching_exact_url_allowlist_and_limit():
    urls = [f"https://srilanka.travel/tourist-attractions?page={number}" for number in range(1, 11)]
    plan = CatalogueBatchPlan(
        batch_id="catalogue_batch_02", source_manifest_path="latest.json", source_manifest_sha256="b" * 64,
        approval_reference="researcher-approved-batch-02", researcher_execution_approved_at="2026-10-16T18:30:00+05:30",
        exact_urls=urls, approved_urls=[CatalogueApprovedUrl(canonical_url=url, authorization_status="approved_for_pilot") for url in urls],
    )
    assert plan.readiness_errors(set(urls)) == []
    mismatch = plan.model_copy(update={"exact_urls": urls[:-1]})
    assert "plan_exact_urls_do_not_match_approved_urls" in mismatch.readiness_errors(set(urls))
    oversized = plan.model_copy(update={"approved_urls": plan.approved_urls + [CatalogueApprovedUrl(canonical_url="https://srilanka.travel/tourist-attractions?page=11", authorization_status="approved_for_pilot")], "exact_urls": urls + ["https://srilanka.travel/tourist-attractions?page=11"]})
    assert "approved_url_plan_exceeds_page_limit" in oversized.readiness_errors(set(urls + ["https://srilanka.travel/tourist-attractions?page=11"]))


def test_duplicate_page_content_and_next_plan_are_deterministic(tmp_path):
    html = b"<div class='attractions-grid'><article class='attraction-card'><h3>One</h3><a href='/attraction&attraction_id=1'>View</a></article></div><div class='attractions-pagination'><a href='/tourist-attractions?page=3'>3</a></div>"
    first = extract_catalogue_page(source_url="https://srilanka.travel/attractions", html=html)
    second = extract_catalogue_page(source_url="https://srilanka.travel/tourist-attractions?page=2", html=html)
    reports = write_catalogue_reports(pages=[first, second], reports_dir=tmp_path, batch_id="duplicates")
    assert second.pagination_content_duplicate is True
    discovery = build_full_discovery_manifest(pages=[first, second])
    assert discovery["remaining_urls"] == ["https://srilanka.travel/tourist-attractions?page=3"]
    plan = write_next_batch_plan(discovery_manifest=discovery, output_path=tmp_path / "next.json", batch_id="next_01", source_manifest_path="manifest.json", source_manifest_sha256="a" * 64)
    assert plan["approved_urls"][0]["authorization_status"] == "discovered_unapproved"
    assert plan["source_manifest_path"] == "manifest.json"
    assert reports["full_discovery_manifest"].exists()


def test_name_whitespace_and_raw_alias_are_preserved():
    page = extract_catalogue_page(source_url="https://srilanka.travel/attractions", html=b"<div class='attractions-grid'><article class='attraction-card'><h3>Gall\n    Fort</h3><a href='/attraction&attraction_id=153'>View</a></article></div>")
    assert page.cards[0].attraction_name == "Gall Fort"
    assert "Gall" in page.cards[0].raw_source_name


def test_researcher_approval_values_reject_placeholders_and_naive_timestamps():
    import pytest
    with pytest.raises(ValueError, match="placeholder timestamp"):
        parse_researcher_approval_timestamp("YOUR_REAL_ISO8601_TIMESTAMP")
    with pytest.raises(ValueError, match="timezone offset"):
        parse_researcher_approval_timestamp("2026-10-16T23:00:00")
    with pytest.raises(ValueError, match="placeholder approval"):
        validate_approval_reference("REPLACE_WITH_APPROVAL")
    assert parse_researcher_approval_timestamp("2026-10-16T23:00:00+05:30").utcoffset() is not None
