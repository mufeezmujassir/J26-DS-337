from datetime import datetime, timezone

from app.time_context.governance.live_pilot import StagedTourismChange
import pytest

from app.time_context.governance.multi_page_pilot import Gate5BPilotPlan, ApprovedPilotUrl, ProcessingStatus, UrlAuthorizationStatus, capture_batch_directory, extract_review_record, repair_listing_scope_contamination, write_captured_html_fixtures


def _plan(*, urls, approved=True):
    return Gate5BPilotPlan(
        approval_reference="researcher-review-2026-10-16",
        researcher_execution_approved_at="2026-10-16T10:00:00+05:30",
        approved_urls=[ApprovedPilotUrl(canonical_url=url, authorization_status=UrlAuthorizationStatus.APPROVED_FOR_PILOT if approved else UrlAuthorizationStatus.DISCOVERED_UNAPPROVED) for url in urls],
    )


def test_plan_requires_each_exact_manifest_url_and_separate_approval():
    plan = _plan(urls=["https://srilanka.travel/attractions"], approved=False)
    errors = plan.readiness_errors({"https://srilanka.travel/attractions"})
    assert "url_not_explicitly_approved:https://srilanka.travel/attractions" in errors
    unknown = _plan(urls=["https://srilanka.travel/not-discovered"])
    assert "url_not_in_gate5a_manifest:https://srilanka.travel/not-discovered" in unknown.readiness_errors(set())


def test_plan_is_limited_to_first_three_urls_and_rejects_duplicates():
    urls = [f"https://srilanka.travel/attraction?attraction_id={n}" for n in range(1, 5)]
    plan = _plan(urls=urls)
    assert "first_pilot_exceeds_three_url_limit" in plan.readiness_errors(set(urls))
    duplicate = _plan(urls=[urls[0], urls[0]])
    assert any(error.startswith("duplicate_url:") for error in duplicate.readiness_errors({urls[0]}))


def test_separate_execution_approval_timestamp_is_required_and_timezone_aware():
    plan = Gate5BPilotPlan(approval_reference="review", approved_urls=[ApprovedPilotUrl(
        canonical_url="https://srilanka.travel/attractions", authorization_status=UrlAuthorizationStatus.APPROVED_FOR_PILOT
    )])
    assert "separate_execution_approval_missing" in plan.readiness_errors({"https://srilanka.travel/attractions"})


def _fetched(url: str, html: str) -> StagedTourismChange:
    return StagedTourismChange(source_url=url, content_sha256="a" * 64, raw_content=html.encode(), http_status=200,
                               retrieved_at=datetime.now(timezone.utc), fetch_success=True)


def test_attraction_detail_extraction_preserves_explicit_id_and_unknowns():
    record = extract_review_record(
        fetched=_fetched("https://srilanka.travel/attraction?attraction_id=163", "<title>Yala</title><h1>Yala National Park</h1><main><p>Official description.</p></main>"),
        candidate={"primary_category": "attraction_detail"}, authorization_reference="test",
    )
    assert record.extracted_fields["source_attraction_id"] == "srilanka_tourism_attraction:163"
    assert record.extracted_fields["district"] is None
    assert record.processing_status is ProcessingStatus.EXTRACTION_REVIEW_REQUIRED
    assert not record.production_write_performed and not record.qdrant_write_performed
    assert record.source_attribution == "Sri Lanka Tourism (srilanka.travel)"


def test_listing_holiday_transport_and_malformed_html_extract_only_supported_fields():
    listing = extract_review_record(
        fetched=_fetched("https://srilanka.travel/attractions", "<h1>Attractions</h1><a href='/attraction?attraction_id=160'>Sigiriya</a>"),
        candidate={"primary_category": "attraction_listing"}, authorization_reference="test",
    )
    reference = listing.extracted_fields["referenced_attractions"][0]
    assert reference["source_attraction_id"] == "srilanka_tourism_attraction:160"
    assert reference["link_text_normalized"] == "Sigiriya"
    assert listing.extracted_fields["listing_description"] is None
    assert "listing_description_unavailable_or_card_scope_rejected" in listing.validation_warnings
    holiday = extract_review_record(
        fetched=_fetched("https://srilanka.travel/index.php?information_id=223&route=information%2Finformation", "<h1>Holiday</h1><p>Poya 2026-05-01</p>"),
        candidate={"primary_category": "public_holidays_poya"}, authorization_reference="test",
    )
    assert holiday.extracted_fields["exact_dates"] == ["2026-05-01"] and holiday.extracted_fields["poya_indicator"] is True
    transport = extract_review_record(
        fetched=_fetched("https://srilanka.travel/getting-around", "<h1>Travel</h1><p>Use bus and train.</p>"),
        candidate={"primary_category": "transportation_travel_information"}, authorization_reference="test",
    )
    assert transport.extracted_fields["transport_modes"] == ["bus", "train"]
    malformed = extract_review_record(
        fetched=_fetched("https://srilanka.travel/wild-safaris", "<html><body><p>broken"),
        candidate={"primary_category": "nature_wildlife"}, authorization_reference="test",
    )
    assert malformed.extracted_fields["page_title"] is None and malformed.validation_warnings


def test_detail_labelled_fields_are_evidence_backed_and_conflicts_warned():
    record = extract_review_record(
        fetched=_fetched("https://srilanka.travel/attraction?attraction_id=163", """
        <h1>Yala</h1><table><tr><th>Location</th><td>South</td></tr><tr><th>Location</th><td>East</td></tr>
        <tr><th>District</th><td>Hambantota</td></tr><tr><th>Opening Hours</th><td>Morning only</td></tr>
        <tr><th>Entry Fee</th><td>1000 LKR</td></tr></table>"""),
        candidate={"primary_category": "attraction_detail"}, authorization_reference="test",
    )
    assert record.extracted_fields["district"] == "Hambantota"
    assert record.extracted_fields["entry_fees"] == "1000 LKR"
    assert "conflicting_location_evidence" in record.validation_warnings
    assert "unparseable_operating_hours" in record.validation_warnings
    assert "missing_fee_information" not in record.validation_warnings


def test_duplicate_listing_references_and_missing_detail_name_are_review_warnings():
    listing = extract_review_record(
        fetched=_fetched("https://srilanka.travel/attractions", "<a href='/attraction?attraction_id=160'>Sigiriya</a><a href='/attraction?attraction_id=160'>Sigiriya</a>"),
        candidate={"primary_category": "attraction_listing"}, authorization_reference="test",
    )
    assert "duplicate_attraction_references_detected:1" in listing.validation_warnings
    detail = extract_review_record(
        fetched=_fetched("https://srilanka.travel/attraction?attraction_id=163", "<table><tr><th>Entry Fee</th><td></td></tr></table>"),
        candidate={"primary_category": "attraction_detail"}, authorization_reference="test",
    )
    assert "missing_attraction_name" in detail.validation_warnings
    assert "missing_fee_information" in detail.validation_warnings


def test_detail_v2_uses_explicit_detail_selector_and_records_diagnostics():
    record = extract_review_record(
        fetched=_fetched("https://srilanka.travel/attraction?attraction_id=163", "<h1>Yala</h1><div class='attraction-description'>Source-supported detail text.</div>"),
        candidate={"primary_category": "attraction_detail"}, authorization_reference="test",
    )
    assert record.extracted_fields["description"] == "Source-supported detail text."
    assert any(item == "checked:.attraction-description:found" for item in record.selector_diagnostics)
    assert record.extraction_adapter_version == "gate5b_v2"


def test_detail_v2_uses_json_ld_but_rejects_generic_paragraphs_as_detail_evidence():
    json_ld = extract_review_record(
        fetched=_fetched("https://srilanka.travel/attraction?attraction_id=163", "<h1>Yala</h1><script type='application/ld+json'>{\"description\": \"Structured source description.\"}</script>"),
        candidate={"primary_category": "attraction_detail"}, authorization_reference="test",
    )
    generic = extract_review_record(
        fetched=_fetched("https://srilanka.travel/attraction?attraction_id=163", "<h1>Yala</h1><main><p>Generic layout text must not be claimed as a detail description.</p></main>"),
        candidate={"primary_category": "attraction_detail"}, authorization_reference="test",
    )
    assert json_ld.extracted_fields["description"] == "Structured source description."
    assert generic.extracted_fields["description"] is None
    assert "detail_content_not_found_by_known_selectors_or_labels_possible_javascript_dependency" in generic.validation_warnings


def test_fixture_capture_is_immutable_and_contains_hash_metadata(tmp_path):
    fetched = [_fetched("https://srilanka.travel/attraction?attraction_id=163", "<h1>Yala</h1>")]
    manifest = write_captured_html_fixtures(fetched=fetched, capture_root=tmp_path, batch_id="batch01_reacquire_v2")
    assert manifest.exists() and "a" * 64 in manifest.read_text()
    with pytest.raises(FileExistsError):
        write_captured_html_fixtures(fetched=fetched, capture_root=tmp_path, batch_id="batch01_reacquire_v2")
    assert capture_batch_directory(capture_root=tmp_path, batch_id="batch01_reacquire_v2").exists()
