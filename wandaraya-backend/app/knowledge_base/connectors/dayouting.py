"""Reference-only connector for the public DayOuting.lk attraction catalogue.

The connector deliberately keeps acquisition separate from promotion into the
recommendation catalogue.  DayOuting's live content signal permits search and
reference use, but forbids AI training.  Callers must therefore retain source
attribution and must never use these records as a model-training corpus.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://dayouting.lk"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
PLACE_SITEMAP_URL = f"{BASE_URL}/xml/travel/single_place.php"
CATEGORY_SITEMAP_URL = f"{BASE_URL}/xml/travel/with-category/sitemap_cat.php"
DETAIL_ENDPOINT = f"{BASE_URL}/clz/search_data_tourist.php"
PLACE_PATH = re.compile(r"^/places-to-visit/(?P<id>\d+)/(?P<slug>[a-z0-9-]+)$", re.I)


SOURCE_CATEGORY_TO_THEME = {
    "Places To Visit": None,
    "Camping Places": "Thrills",
    "Hiking Areas": "Thrills",
    "Waterfalls": "Scenic",
    "Festival": "Festive",
    "Historical Places": "Heritage",
    "Street Foods": "Essence",
    "Bird Watching": "Wild",
    "Wildlife": "Wild",
    "Beaches": "Pristine",
    "Adventure": "Thrills",
    "Bathing Places": "Pristine",
    "Places to Visit by Train": "Scenic",
}

KEYWORD_THEMES = {
    "Heritage": ("temple", "kovil", "vihara", "church", "mosque", "fort", "museum", "monastery", "ancient", "histor", "archaeolog", "palace"),
    "Wild": ("wildlife", "bird", "safari", "elephant", "whale", "dolphin", "sanctuary", "national park"),
    "Thrills": ("hike", "hiking", "camp", "climb", "adventure", "rafting", "zipline", "mountain"),
    "Pristine": ("beach", "bathing", "swim", "lagoon", "coast"),
    "Scenic": ("waterfall", "viewpoint", "view point", "scenic", "train", "lake", "reservoir"),
    "Festive": ("festival", "perahera", "celebration"),
    "Essence": ("food", "market", "culinary", "village", "craft"),
    "Bliss": ("spa", "wellness", "ayurveda", "meditation", "retreat"),
}


class DayOutingPolicyError(RuntimeError):
    """Raised when the live site policy is incompatible with this connector."""


@dataclass(slots=True)
class DayOutingPlace:
    source_id: str
    slug: str
    source_url: str
    name: str
    description: str
    province: str | None = None
    district: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    map_url: str | None = None
    video_url: str | None = None
    image_urls: list[str] = field(default_factory=list)
    source_categories: list[str] = field(default_factory=list)
    mapped_theme: str | None = None
    mapping_method: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_source_category(slug: str) -> str:
    special = {
        "places-to-visit": "Places To Visit",
        "places-to-visit-by-train": "Places to Visit by Train",
    }
    return special.get(slug.casefold(), slug.replace("-", " ").title())


def map_theme(categories: Iterable[str], name: str, description: str) -> tuple[str | None, str]:
    specific = sorted({SOURCE_CATEGORY_TO_THEME.get(category) for category in categories if SOURCE_CATEGORY_TO_THEME.get(category)})
    if len(specific) == 1:
        return specific[0], "dayouting_source_category"
    text = f"{name} {description}".casefold()
    scores = {theme: sum(1 for word in words if word in text) for theme, words in KEYWORD_THEMES.items()}
    best = max(scores, key=scores.get)
    if scores[best] > 0 and list(scores.values()).count(scores[best]) == 1:
        return best, "deterministic_keyword_rule"
    if specific:
        # Conflicting memberships are not resolved by an LLM automatically.
        return specific[0], "ambiguous_source_categories_review_required"
    return None, "manual_or_llm_review_required"


class DayOutingCatalogue:
    def __init__(self, *, delay_seconds: float = 0.35, timeout_seconds: float = 30.0, session: requests.Session | None = None):
        self.delay_seconds = max(0.0, delay_seconds)
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "WANDARAYA-Academic-Reference-Importer/1.0 (+source-attributed tourism research)",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last_request = 0.0

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        response = self.session.request(method, url, timeout=self.timeout_seconds, **kwargs)
        self._last_request = time.monotonic()
        response.raise_for_status()
        return response

    def verify_live_policy(self) -> dict[str, str]:
        text = self._request("GET", ROBOTS_URL).text
        signal_match = re.search(r"(?im)^Content-Signal:\s*(.+)$", text)
        if not signal_match:
            raise DayOutingPolicyError("DayOuting robots.txt has no Content-Signal; acquisition is stopped for manual review.")
        signals = {}
        for item in signal_match.group(1).split(","):
            key, _, value = item.strip().partition("=")
            signals[key.casefold()] = value.casefold()
        if signals.get("search") != "yes" or signals.get("ai-train") != "no":
            raise DayOutingPolicyError(f"Unexpected DayOuting content signals: {signals}")
        if not re.search(r"(?ims)^User-agent:\s*\*.*?^Allow:\s*/\s*$", text):
            raise DayOutingPolicyError("DayOuting no longer grants general crawler access.")
        return signals

    def place_urls(self) -> list[str]:
        xml = BeautifulSoup(self._request("GET", PLACE_SITEMAP_URL).content, "xml")
        urls = []
        for loc in xml.find_all("loc"):
            url = loc.get_text(strip=True).replace("http://", "https://", 1)
            parsed = urlparse(url)
            if parsed.hostname not in {"dayouting.lk", "www.dayouting.lk"} or not PLACE_PATH.match(parsed.path):
                continue
            urls.append(f"{BASE_URL}{parsed.path}")
        return list(dict.fromkeys(urls))

    def category_names(self) -> list[str]:
        xml = BeautifulSoup(self._request("GET", CATEGORY_SITEMAP_URL).content, "xml")
        names = []
        for loc in xml.find_all("loc"):
            path = urlparse(loc.get_text(strip=True)).path.rstrip("/")
            if path.casefold().startswith("/visit/"):
                names.append(normalize_source_category(path.rsplit("/", 1)[-1]))
        return list(dict.fromkeys(names))

    def category_memberships(self, categories: Iterable[str] | None = None, *, page_size: int = 10) -> dict[str, list[str]]:
        # The legacy endpoint returns an empty body when ``e`` is greater than
        # ten, so its server-side page size must be respected.
        page_size = min(10, max(1, page_size))
        memberships: dict[str, list[str]] = {}
        for category in categories or self.category_names():
            offset = 0
            while True:
                response = self._request("POST", DETAIL_ENDPOINT, data={
                    "ref": "search_by_categories", "province": "0", "district": "0", "city": "0",
                    "cat": category, "s": offset, "e": page_size,
                })
                soup = BeautifulSoup(response.text, "html.parser")
                found: list[str] = []
                for node in soup.select("[onclick]"):
                    match = re.search(r"get_share_link\((\d+)", node.get("onclick", ""))
                    if match:
                        found.append(match.group(1))
                found = list(dict.fromkeys(found))
                for source_id in found:
                    memberships.setdefault(source_id, []).append(category)
                if len(found) < page_size:
                    break
                offset += page_size
        return memberships

    def fetch_place(self, url: str, categories: Iterable[str] = ()) -> DayOutingPlace:
        parsed = urlparse(url)
        match = PLACE_PATH.match(parsed.path)
        if parsed.hostname not in {"dayouting.lk", "www.dayouting.lk"} or not match:
            raise ValueError(f"Not an approved DayOuting place URL: {url}")
        source_id = match.group("id")
        response = self._request("POST", DETAIL_ENDPOINT, data={"ref": "search_by_place-id", "placeid": source_id})
        soup = BeautifulSoup(response.text, "html.parser")
        root = soup.select_one('[itemtype="http://schema.org/TouristAttraction"]')
        if root is None:
            raise ValueError(f"DayOuting returned no TouristAttraction for source id {source_id}")

        def text(selector: str) -> str | None:
            node = root.select_one(selector)
            return node.get_text(" ", strip=True) if node else None

        name = text('[itemprop="name"]') or ""
        description = text('[itemprop="description"]') or ""
        images = [urljoin(BASE_URL + "/", node.get("src")) for node in root.select('[itemprop="image"][src]')]
        province_node = root.select_one('a[title$=" Province"]')
        province = province_node.get("title", "").removesuffix(" Province").strip() if province_node else None
        district = text('[itemprop="addressRegion"]')
        city = text('[itemprop="addressLocality"]')
        map_url = video_url = None
        for node in root.select("[onclick]"):
            onclick = node.get("onclick", "")
            map_match = re.search(r"view_gmap_location\('([^']+)'", onclick)
            video_match = re.search(r"watch_yt_video\('([^']+)'", onclick)
            if map_match:
                map_url = map_match.group(1)
            if video_match:
                video_url = video_match.group(1)
        latitude = longitude = None
        if map_url:
            coordinate_match = re.search(r"!2d(-?\d+(?:\.\d+)?)!3d(-?\d+(?:\.\d+)?)", map_url)
            if coordinate_match:
                longitude, latitude = map(float, coordinate_match.groups())
        source_categories = list(dict.fromkeys(categories))
        theme, method = map_theme(source_categories, name, description)
        if not name or len(description) < 20:
            raise ValueError(f"Incomplete DayOuting record {source_id}: name/description missing")
        return DayOutingPlace(
            source_id=source_id, slug=match.group("slug"), source_url=f"{BASE_URL}{parsed.path}",
            name=name, description=description, province=province, district=district, city=city,
            latitude=latitude, longitude=longitude, map_url=map_url, video_url=video_url,
            image_urls=list(dict.fromkeys(images)), source_categories=source_categories,
            mapped_theme=theme, mapping_method=method,
        )
