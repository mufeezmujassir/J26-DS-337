import pytest

from app.time_context.governance.url_intelligence import (
    ExistingAttractionReference, ReconciliationStatus, TourismUrlCategory,
    build_url_inventory, canonicalize_tourism_url, classify_tourism_url,
)


@pytest.mark.parametrize(("url", "text", "expected"), [
    ("https://www.srilanka.travel/pristine-beach-holidays", "Pristine", TourismUrlCategory.BEACH_MARINE),
    ("https://srilanka.travel/wild-safaris", "Wild Safaris", TourismUrlCategory.NATURE_WILDLIFE),
    ("https://srilanka.travel/whale-watching", "Whale Watching", TourismUrlCategory.BEACH_MARINE),
    ("https://srilanka.travel/adventure-sports", "Adventure", TourismUrlCategory.ADVENTURE_OUTDOOR),
    ("https://srilanka.travel/top-cities-and-provinces", "Cities", TourismUrlCategory.DESTINATION),
    ("https://srilanka.travel/transport", "Transport", TourismUrlCategory.TRANSPORT_TRAVEL),
    ("https://srilanka.travel/Key_Contacts", "Key Contacts", TourismUrlCategory.ADMINISTRATIVE_CORPORATE),
    ("https://srilanka.travel/attractions", "All Attractions", TourismUrlCategory.ATTRACTION_LISTING),
    ("https://srilanka.travel/attraction?attraction_id=163", "Yala", TourismUrlCategory.ATTRACTION_DETAIL),
    ("https://srilanka.travel/index.php?route=information/information&information_id=223", "Public Holidays in Sri Lanka", TourismUrlCategory.PUBLIC_HOLIDAYS_POYA),
    ("https://srilanka.travel/index.php?route=event/upcoming&dev=asd", "Upcoming Events", TourismUrlCategory.EVENTS_FESTIVALS),
    ("https://srilanka.travel/what-to-do", "What to do", TourismUrlCategory.ACTIVITY_LISTING),
    ("https://srilanka.travel/sitemap", "Site map", TourismUrlCategory.NAVIGATION_DISCOVERY),
    ("https://srilanka.travel/terms-and-conditions", "Terms", TourismUrlCategory.LEGAL_GOVERNANCE),
    ("https://srilanka.travel/tourist-guides", "Tourist guides", TourismUrlCategory.ACCOMMODATION_SERVICES),
])
def test_manually_labelled_regression_sample(url, text, expected):
    assert classify_tourism_url(url, text)[0] is expected


def test_canonicalization_preserves_meaningful_ids_and_rejects_external_urls():
    canonical = canonicalize_tourism_url("http://www.srilanka.travel/attraction?z=2&attraction_id=163#x")
    assert canonical == "https://srilanka.travel/attraction?attraction_id=163&z=2"
    with pytest.raises(ValueError):
        canonicalize_tourism_url("mailto:info@example.com")
    with pytest.raises(ValueError):
        canonicalize_tourism_url("https://example.com/attractions")


def test_inventory_deduplicates_hosts_and_is_read_only_by_default():
    discovered = {"raw_link_count": 3, "external_link_count": 0, "duplicate_internal_link_count": 0, "category_distribution": {}, "candidates": [
        {"url": "https://www.srilanka.travel/attraction?attraction_id=163", "link_text": "Yala"},
        {"url": "https://srilanka.travel/attraction?attraction_id=163", "link_text": "Yala National Park"},
        {"url": "https://srilanka.travel/attractions", "link_text": "All"},
    ]}
    items, audit = build_url_inventory(discovered)
    assert len(items) == 2 and audit["cross_hostname_or_canonical_duplicates"] == 1
    detail = items[0]
    assert detail.authorization_status == "discovered_unapproved"
    assert detail.reconciliation_status is ReconciliationStatus.INSUFFICIENT_EVIDENCE


def test_researcher_selected_preferred_urls_get_review_priorities_only_when_discovered():
    discovered = {"candidates": [
        {"url": "https://srilanka.travel/attractions", "link_text": "All attractions"},
        {"url": "https://srilanka.travel/attraction?attraction_id=163", "link_text": "Yala"},
    ]}
    items, _ = build_url_inventory(discovered)
    priorities = {item.canonical_url: item.proposed_acquisition_priority for item in items}
    assert priorities["https://srilanka.travel/attractions"] == 1
    assert priorities["https://srilanka.travel/attraction?attraction_id=163"] == 3


def test_read_only_reconciliation_can_use_existing_source_mapping_without_writes():
    discovered = {"candidates": [{"url": "https://srilanka.travel/attraction?attraction_id=163", "link_text": "Yala"}]}
    existing = [ExistingAttractionReference(attraction_id=4, name="Yala", external_source_id="srilanka_tourism_attraction:163")]
    items, _ = build_url_inventory(discovered, existing=existing)
    assert items[0].reconciliation_status is ReconciliationStatus.EXISTING_ENTITY_MATCH
