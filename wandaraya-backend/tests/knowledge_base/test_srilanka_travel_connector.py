import pytest

from app.knowledge_base.connectors.srilanka_travel import (
    SriLankaTravelCatalogue,
    catalogue_url_from_sitemap,
    extract_sitemap_urls,
)


DETAIL = """
<section class="attraction-hero">
  <div class="attraction-hero-bg" style="background-image: url('http://srilanka.travel//image/main.jpg')"></div>
  <div class="attraction-hero-content"><h1>Official Temple</h1></div>
</section>
<div class="info-breadcrumb">
  <a href="/">Home</a>
  <a href="index.php?route=attractions/destination&destination=8">Jaffna</a>
  <a href="index.php?route=attractions/theme&destination=8&theme=2">Heritage</a>
</div>
<div class="info-content-card"><div class="content-inner">
  <div><p>Verified official description.</p></div>
  <div id="more">More</div>
  <div id="full_description"><p>Additional visitor guidance.</p></div>
  <h4>Useful Information</h4>
  <ul class="attraction-data"><li><strong>Entrance Fees:</strong> 10 USD</li></ul>
</div></div>
<ul class="attr-gallery-list"><li><a href="http://srilanka.travel//image/gallery.jpg">Photo</a></li></ul>
<script>center: new google.maps.LatLng(9.6129, 79.7696)</script>
"""


def test_detail_parser_preserves_official_identity_description_theme_and_images():
    result = SriLankaTravelCatalogue(delay_seconds=0).parse_detail(
        DETAIL, "https://srilanka.travel/attraction&attraction_id=19"
    )
    assert result.source_id == "19"
    assert result.name == "Official Temple"
    assert result.destination == "Jaffna"
    assert result.theme == "Heritage"
    assert result.description == "Verified official description.\n\nAdditional visitor guidance."
    assert result.useful_information == {"Entrance Fees": "10 USD"}
    assert result.images == [
        "https://srilanka.travel/image/main.jpg",
        "https://srilanka.travel/image/gallery.jpg",
    ]
    assert result.latitude == 9.6129
    assert result.longitude == 79.7696


def test_extract_pasted_sitemap_and_locate_catalogue():
    pasted = """This XML file does not appear to have any style information.
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://www.srilanka.travel/about-us</loc></url>
      <url><loc>https://www.srilanka.travel/attractions</loc></url>
      <url><loc>https://example.com/not-approved</loc></url>
    </urlset>"""
    assert extract_sitemap_urls(pasted) == [
        "https://srilanka.travel/about-us",
        "https://srilanka.travel/attractions",
    ]
    assert catalogue_url_from_sitemap(pasted) == "https://srilanka.travel/attractions"


def test_sitemap_without_catalogue_is_rejected():
    sitemap = "<urlset><url><loc>https://www.srilanka.travel/about-us</loc></url></urlset>"
    with pytest.raises(ValueError, match="/attractions"):
        catalogue_url_from_sitemap(sitemap)


def test_legacy_sitemap_with_bare_ampersand_is_tolerated():
    sitemap = """<urlset>
      <url><loc>https://www.srilanka.travel/bliss-nature-trails&article=56</loc></url>
      <url><loc>https://www.srilanka.travel/attractions</loc></url>
    </urlset>"""
    assert catalogue_url_from_sitemap(sitemap) == "https://srilanka.travel/attractions"
