from app.holiday_event.parsers import parse_calendar_html, parse_lankaevents_html
from app.holiday_event.source_access import check_source_access


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
