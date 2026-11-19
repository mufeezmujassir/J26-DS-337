from __future__ import annotations

from app.knowledge_base.connectors.dayouting import DayOutingCatalogue, map_theme, normalize_source_category


DETAIL_HTML = """
<div itemscope itemtype="http://schema.org/TouristAttraction">
 <h1 itemprop="name">Nuwaragala Mountain</h1>
 <p itemprop="description">An ancient fortress and monastery with a stone pathway and a large cave in Ampara.</p>
 <img itemprop="image" src="img_uploads/tourist-places/example.jpg">
 <a title="Eastern Province">Eastern</a>
 <span itemprop="addressRegion">Ampara</span>
 <span itemprop="addressLocality">Maha Oya</span>
 <a onclick="view_gmap_location('https://maps.test/embed?x=!2d81.460085!3d7.509337','Nuwaragala')">Map</a>
 <a onclick="watch_yt_video('https://youtu.be/example','Nuwaragala')">Video</a>
</div>
"""


class FakeResponse:
    text = DETAIL_HTML

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.headers = {}

    def request(self, method, url, timeout, **kwargs):
        assert kwargs["data"] == {"ref": "search_by_place-id", "placeid": "1202"}
        return FakeResponse()


def test_parse_structured_detail_and_coordinates():
    connector = DayOutingCatalogue(delay_seconds=0, session=FakeSession())
    record = connector.fetch_place(
        "https://dayouting.lk/places-to-visit/1202/nuwaragala-mountain",
        ["Historical Places", "Hiking Areas"],
    )
    assert record.source_id == "1202"
    assert record.district == "Ampara"
    assert record.city == "Maha Oya"
    assert record.latitude == 7.509337
    assert record.longitude == 81.460085
    assert record.image_urls == ["https://dayouting.lk/img_uploads/tourist-places/example.jpg"]
    assert record.mapped_theme == "Heritage"
    assert record.mapping_method == "deterministic_keyword_rule"


def test_deterministic_category_and_keyword_mapping():
    assert normalize_source_category("places-to-visit-by-train") == "Places to Visit by Train"
    assert map_theme(["Beaches"], "Example", "A coast") == ("Pristine", "dayouting_source_category")
    assert map_theme(["Places To Visit"], "Ancient Temple", "A historic monastery") == (
        "Heritage", "deterministic_keyword_rule"
    )


def test_rejects_non_catalogue_url():
    connector = DayOutingCatalogue(delay_seconds=0, session=FakeSession())
    try:
        connector.fetch_place("https://example.com/places-to-visit/1202/nuwaragala-mountain")
    except ValueError as exc:
        assert "approved DayOuting" in str(exc)
    else:
        raise AssertionError("expected URL validation failure")
