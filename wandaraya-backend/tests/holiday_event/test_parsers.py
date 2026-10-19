from app.holiday_event.parsers import parse_calendar_html, parse_lankaevents_detail_html, parse_lankaevents_html
from app.holiday_event.source_access import TermsReview, check_source_access, evaluate_robots_response
from app.holiday_event.repository import holiday_source_values, json_safe
from app.holiday_event.schemas import HolidayRecord
import httpx
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID


def test_calendar_parses_poya_and_tentative():
    rows = parse_calendar_html("<table><tr><th>Date</th><th>Holiday</th></tr><tr><td>30 May</td><td>Vesak Full Moon Poya Day</td></tr><tr><td>28 May</td><td>Eid al-Adha*</td></tr></table>", source_url="https://calendarsrilanka.com/", year=2026)
    assert len(rows) == 2
    assert rows[0].poya_name == "Vesak"
    assert rows[1].confirmation_status == "tentative"


def test_event_parser_requires_visible_event_evidence():
    rows = parse_lankaevents_html('<div><a href="/events/yala-2026">WNPS Field Trip-Yala</a><span>Fri, 13 Nov 2026</span></div>', source_url="https://lankaevents.lk/")
    assert len(rows) == 1
    assert rows[0].source_url == "https://lankaevents.lk/events/yala-2026"


def test_source_access_is_gated_not_bypassed():
    assert check_source_access("calendar_sri_lanka", "https://calendarsrilanka.com/")["permitted"] is False
    assert check_source_access("third_source_placeholder", "https://example.test/")["reason"] == "source_not_configured"


def test_runtime_access_stops_when_robots_is_unavailable():
    base = check_source_access("calendar_sri_lanka", "https://calendarsrilanka.com/")
    assert evaluate_robots_response(base, httpx.Response(404), "https://calendarsrilanka.com/robots.txt")["reason"] == "NO_ROBOTS_RULES_FOUND:terms_review_required"


def test_missing_robots_is_distinct_from_a_terms_authorized_source():
    base = check_source_access("lanka_events", "https://lankaevents.lk/")
    result = evaluate_robots_response(base, httpx.Response(404), "https://lankaevents.lk/robots.txt", terms_review=TermsReview(True, True, "https://source.test/terms", "2026-10-19T10:00:00+05:30"))
    assert result["permitted"] is True
    assert result["reason"] == "NO_ROBOTS_RULES_FOUND"


def test_disallow_and_rate_limit_are_not_enabled_by_terms_review():
    base = check_source_access("calendar_sri_lanka", "https://calendarsrilanka.com/")
    review = TermsReview(True, True, "terms-review-2026-10-19")
    assert evaluate_robots_response(base, httpx.Response(429), "https://calendarsrilanka.com/robots.txt", terms_review=review)["reason"] == "ACCESS_BLOCKED:robots_rate_limited"
    assert evaluate_robots_response(base, httpx.Response(200, text="User-agent: *\nDisallow: /"), "https://calendarsrilanka.com/robots.txt", terms_review=review)["reason"] == "ACCESS_BLOCKED:robots_target_disallowed"


def test_admin_rule_does_not_block_the_public_calendar_root():
    base = check_source_access("calendar_sri_lanka", "https://calendarsrilanka.com/")
    review = TermsReview(True, True, "https://source.test/terms", "2026-10-19T10:00:00+05:30")
    result = evaluate_robots_response(base, httpx.Response(200, text="User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php"), "https://calendarsrilanka.com/robots.txt", terms_review=review)
    assert result["permitted"] is True


def test_placeholder_or_undated_terms_evidence_does_not_authorize_collection():
    base = check_source_access("calendar_sri_lanka", "https://calendarsrilanka.com/")
    review = TermsReview(True, True, "REPLACE_WITH_REVIEWED_PUBLIC_TERMS_URL_OR_RECORDED_PERMISSION")
    result = evaluate_robots_response(base, httpx.Response(200, text="User-agent: *\nAllow: /"), "https://calendarsrilanka.com/robots.txt", terms_review=review)
    assert result["reason"] == "ACCESS_BLOCKED:terms_evidence_incomplete"

    actual_placeholder = TermsReview(True, True, "ACTUAL_TERMS_URL_OR_WRITTEN_PERMISSION_REFERENCE", "2026-10-19T10:00:00+05:30")
    actual_result = evaluate_robots_response(base, httpx.Response(200, text="User-agent: *\nAllow: /"), "https://calendarsrilanka.com/robots.txt", terms_review=actual_placeholder)
    assert actual_result["reason"] == "ACCESS_BLOCKED:terms_evidence_incomplete"


def test_revision_payloads_are_json_safe_for_nested_supported_values():
    class State(Enum):
        CONFIRMED = "confirmed"
    payload = json_safe({
        "date": date(2026, 1, 3),
        "nested": [datetime(2026, 1, 3, 10, 30, tzinfo=timezone.utc), Decimal("12.50"), UUID("12345678-1234-5678-1234-567812345678"), State.CONFIRMED],
    })
    assert payload == {
        "date": "2026-01-03",
        "nested": ["2026-01-03T10:30:00+00:00", "12.50", "12345678-1234-5678-1234-567812345678", "confirmed"],
    }


def test_holiday_source_values_exclude_observation_metadata():
    record = HolidayRecord(holiday_date=date(2026, 5, 1), holiday_name="Fixture Holiday", holiday_type="holiday", source_url="https://source.test/", source_updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    values = holiday_source_values(record)
    assert "last_seen_at" not in values
    assert values["source_updated_at"] == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_attested_verbal_calendar_authorization_is_distinct_from_terms():
    base = check_source_access("calendar_sri_lanka", "https://calendarsrilanka.com/")
    authorization = TermsReview(
        reviewed=False,
        automated_collection_permitted=False,
        authorization_type="verbal_permission",
        authorization_status="user_attested",
        authorization_evidence="Project owner reports verbal authorization from the website operator during a phone call.",
        authorization_scope="Public Sri Lankan calendar, holidays and Poya-day information for WANDARAYA ingestion.",
        standing_authorization=True,
    )
    result = evaluate_robots_response(base, httpx.Response(200, text="User-agent: *\nDisallow: /wp-admin/"), "https://calendarsrilanka.com/robots.txt", terms_review=authorization)
    assert result["permitted"] is True
    assert result["reason"] == "AUTHORIZED_PUBLIC_CALENDAR_INGESTION"
    assert result["authorization_status"] == "user_attested"


def test_detail_parser_extracts_only_visible_labeled_fields():
    html = """<h1>Fixture Art Exhibition</h1><dl><dt>Venue</dt><dd>Example Gallery</dd><dt>Date</dt><dd>01 Oct 2026 - 21 Oct 2026</dd><dt>Time</dt><dd>08:00 AM to 05:00 PM</dd><dt>Organizer</dt><dd>Fixture Organizer</dd><dt>Notes</dt><dd>#Art #Colombo Public description.</dd></dl>"""
    record = parse_lankaevents_detail_html(html, source_url="https://lankaevents.lk/public-event?id=999")
    assert record is not None
    assert record.source_event_id == "999"
    assert record.venue == "Example Gallery"
    assert record.start_datetime is not None
    assert record.hashtags == ["#Art", "#Colombo"]
