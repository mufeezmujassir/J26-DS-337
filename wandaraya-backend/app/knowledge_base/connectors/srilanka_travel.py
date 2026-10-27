"""Polite, deterministic reader for the official Sri Lanka Tourism catalogue.

The catalogue is the identity authority.  Google Places may enrich an already
identified attraction, but it must never create attractions by nearby search.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://srilanka.travel"
CATALOGUE_URL = f"{BASE_URL}/attractions"
THEMES = {
    "1": "Pristine",
    "2": "Heritage",
    "3": "Wild",
    "4": "Thrills",
    "5": "Bliss",
    "6": "Scenic",
    "7": "Festive",
    "8": "Essence",
}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.replace("\xa0", " ").split())
    return cleaned or None


def _https(url: str, source_url: str = BASE_URL) -> str:
    absolute = urljoin(source_url, url).replace("http://", "https://", 1)
    return absolute.replace("srilanka.travel//image/", "srilanka.travel/image/")


def extract_sitemap_urls(xml_text: str) -> list[str]:
    """Extract unique, same-site HTTPS URLs from a sitemap export.

    Raw XML copied from a browser can include a human-readable warning before
    the root element. That prefix is ignored, while off-domain URLs are always
    rejected from this official-source discovery input.
    """
    start = xml_text.find("<urlset")
    if start < 0:
        start = xml_text.find("<sitemapindex")
    if start < 0:
        raise ValueError("The supplied file is not an XML sitemap.")
    document = xml_text[start:]
    raw_locations: list[str]
    try:
        root = ET.fromstring(document)
        raw_locations = [
            element.text.strip()
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] == "loc" and element.text
        ]
    except ET.ParseError:
        # The official export contains legacy URLs with bare ampersands, which
        # are invalid XML but still unambiguous inside a <loc> element.
        raw_locations = [
            unescape(match.group(1).strip())
            for match in re.finditer(r"<loc>\s*(.*?)\s*</loc>", document, re.IGNORECASE | re.DOTALL)
        ]
    if not raw_locations:
        raise ValueError("The supplied sitemap does not contain any URL locations.")

    found: list[str] = []
    for location in raw_locations:
        parsed = urlparse(location)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "srilanka.travel", "www.srilanka.travel",
        }:
            continue
        canonical = f"https://srilanka.travel{parsed.path or '/'}"
        if parsed.query:
            canonical = f"{canonical}?{parsed.query}"
        found.append(canonical)
    return list(dict.fromkeys(found))


def catalogue_url_from_sitemap(xml_text: str) -> str:
    """Find the canonical attraction-catalogue entry in a sitemap."""
    for url in extract_sitemap_urls(xml_text):
        if urlparse(url).path.rstrip("/") == "/attractions":
            return url
    raise ValueError("The sitemap does not contain the official /attractions catalogue entry.")


@dataclass(slots=True)
class OfficialAttraction:
    source_id: str
    source_url: str
    name: str
    destination: str | None
    theme: str | None
    description: str
    latitude: float | None
    longitude: float | None
    images: list[str] = field(default_factory=list)
    useful_information: dict[str, str] = field(default_factory=dict)


class SriLankaTravelCatalogue:
    def __init__(self, *, delay_seconds: float = 0.25, timeout_seconds: float = 30.0):
        self.delay_seconds = max(0.0, delay_seconds)
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "WANDARAYA-Academic-Research/1.0 (+local research ingestion; contact site owner)",
            "Accept-Language": "en",
        })

    def _get(self, url: str) -> tuple[str, str]:
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", "").casefold():
            raise ValueError(f"Expected HTML from {url}")
        time.sleep(self.delay_seconds)
        return response.text, str(response.url)

    def discover_detail_urls(self, *, sitemap_xml: str | None = None) -> list[str]:
        found: dict[str, str] = {}
        expected_total = 169
        catalogue_url = catalogue_url_from_sitemap(sitemap_xml) if sitemap_xml else CATALOGUE_URL
        # The public catalogue randomises card order even when a page parameter
        # is supplied. Repeat the finite 15-page traversal and de-duplicate by
        # the official attraction_id until the advertised total is reached.
        for _round in range(12):
            for page in range(1, 16):
                url = catalogue_url if page == 1 else f"{catalogue_url}?page={page}"
                html, _ = self._get(url)
                # The live catalogue contains malformed legacy markup that lxml may
                # discard wholesale; Python's tolerant HTML parser preserves cards.
                soup = BeautifulSoup(html, "html.parser")
                if page == 1:
                    text = soup.get_text(" ", strip=True)
                    total_match = re.search(r"Showing\s+\d+\s+to\s+\d+\s+of\s+(\d+)", text, re.IGNORECASE)
                    if total_match:
                        expected_total = int(total_match.group(1))
                for card in soup.select(".attractions-grid article.attraction-card"):
                    anchor = card.select_one("a[href*='attraction_id=']")
                    if anchor is None:
                        continue
                    match = re.search(r"attraction_id=(\d+)", anchor.get("href", ""))
                    if match:
                        source_id = match.group(1)
                        found[source_id] = f"{BASE_URL}/attraction&attraction_id={source_id}"
            if len(found) >= expected_total:
                break
        if len(found) != expected_total:
            raise ValueError(
                f"Catalogue discovery returned {len(found)} of {expected_total} unique attractions; refusing partial import."
            )
        return [found[key] for key in sorted(found, key=int)]

    def parse_detail(self, html: str, source_url: str) -> OfficialAttraction:
        soup = BeautifulSoup(html, "html.parser")
        match = re.search(r"attraction_id=(\d+)", source_url)
        if not match:
            raise ValueError(f"Missing official attraction id in {source_url}")
        heading = soup.select_one(".attraction-hero-content h1, h1")
        name = _clean(heading.get_text(" ", strip=True) if heading else None)
        if not name:
            raise ValueError(f"Missing attraction name in {source_url}")

        destination = None
        theme = None
        for anchor in soup.select(".info-breadcrumb a[href]"):
            href = anchor.get("href", "")
            value = _clean(anchor.get_text(" ", strip=True))
            if "attractions/destination" in href:
                destination = value
            elif "attractions/theme" in href:
                theme = value

        content = soup.select_one(".info-content-card .content-inner")
        description_parts: list[str] = []
        if content:
            for child in content.find_all("div", recursive=False):
                if child.get("id") in {"more", "hide"}:
                    continue
                text = _clean(child.get_text(" ", strip=True))
                if text:
                    description_parts.append(text)
        description = "\n\n".join(dict.fromkeys(description_parts))
        if not description:
            raise ValueError(f"Missing official description in {source_url}")

        useful: dict[str, str] = {}
        for item in soup.select("ul.attraction-data li"):
            strong = item.find("strong")
            if strong:
                key = _clean(strong.get_text(" ", strip=True).rstrip(":"))
                strong.extract()
                value = _clean(item.get_text(" ", strip=True))
                if key and value:
                    useful[key] = value

        images: list[str] = []
        hero = soup.select_one(".attraction-hero-bg[style]")
        if hero:
            image_match = re.search(r"url\(['\"]?([^'\")]+)", hero.get("style", ""))
            if image_match:
                images.append(_https(image_match.group(1), source_url))
        for anchor in soup.select(".attr-gallery-list a[href]"):
            images.append(_https(anchor["href"], source_url))
        images = list(dict.fromkeys(images))

        coordinates = re.search(
            r"center:\s*new\s+google\.maps\.LatLng\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
            html,
        )
        latitude = float(coordinates.group(1)) if coordinates else None
        longitude = float(coordinates.group(2)) if coordinates else None
        if theme not in THEMES.values():
            theme = None
        return OfficialAttraction(
            source_id=match.group(1), source_url=source_url, name=name,
            destination=destination, theme=theme, description=description,
            latitude=latitude, longitude=longitude, images=images,
            useful_information=useful,
        )

    def fetch_all(self, *, sitemap_xml: str | None = None) -> list[OfficialAttraction]:
        records: list[OfficialAttraction] = []
        for url in self.discover_detail_urls(sitemap_xml=sitemap_xml):
            html, _ = self._get(url)
            records.append(self.parse_detail(html, url))
        if len(records) != len({item.source_id for item in records}):
            raise ValueError("Duplicate official attraction identities were returned.")
        return records
