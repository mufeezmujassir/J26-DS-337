import os
import re
import csv
import logging
from typing import Optional, Tuple, Dict, Any
import httpx

logger = logging.getLogger(__name__)

class IslandGeocoder:
    """
    All-Island Sri Lanka Geocoder and Location Resolver.
    
    Tiers of resolution:
    1. Direct decimal coordinates (e.g., '6.0367, 80.2170' or '9.6651, 80.0093')
    2. High-speed local gazetteer of 6,900+ Sri Lankan cities, towns, villages, and hamlets
       loaded from GIS OSM datasets (includes Jaffna, Point Pedro, Trincomalee, Badulla, etc.)
    3. Railway stations and bus interchange terminals
    4. Dynamic OpenStreetMap Nominatim geocoding fallback for arbitrary landmarks
    """
    _instance = None
    _gazetteer: Dict[str, Tuple[float, float, str, str]] = {}
    _initialized = False

    def __init__(self, data_dir: Optional[str] = None):
        if not IslandGeocoder._initialized:
            self._data_dir = data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            self._load_local_gazetteer()
            IslandGeocoder._initialized = True

    @classmethod
    def get_instance(cls) -> "IslandGeocoder":
        if cls._instance is None:
            cls._instance = IslandGeocoder()
        return cls._instance

    def _load_local_gazetteer(self):
        """Loads places from GIS OSM places CSV into an in-memory dictionary."""
        places_csv = os.path.join(self._data_dir, "scenic", "gis_osm_places_free_1.csv")
        wkt_regex = re.compile(r"POINT\s*\(\s*([-\d\.]+)\s+([-\d\.]+)\s*\)", re.IGNORECASE)

        # Standard major Sri Lanka city coordinates baseline for instant resolution
        baseline = {
            "colombo": (6.9271, 79.8612, "Colombo", "city"),
            "colombo fort": (6.9344, 79.8428, "Colombo Fort", "transport_hub"),
            "jaffna": (9.6651, 80.0093, "Jaffna", "city"),
            "galle": (6.0535, 80.2210, "Galle", "city"),
            "matara": (5.9549, 80.5550, "Matara", "city"),
            "kandy": (7.2906, 80.6337, "Kandy", "city"),
            "negombo": (7.2083, 79.8358, "Negombo", "city"),
            "anuradhapura": (8.3114, 80.4037, "Anuradhapura", "city"),
            "trincomalee": (8.5874, 81.2152, "Trincomalee", "city"),
            "batticaloa": (7.7310, 81.6747, "Batticaloa", "city"),
            "badulla": (6.9934, 81.0550, "Badulla", "city"),
            "nuwara eliya": (6.9497, 80.7891, "Nuwara Eliya", "city"),
            "ella": (6.8667, 81.0466, "Ella", "town"),
            "kurunegala": (7.4863, 80.3623, "Kurunegala", "city"),
            "ratnapura": (6.7056, 80.3847, "Ratnapura", "city"),
            "vavuniya": (8.7514, 80.4971, "Vavuniya", "city"),
            "kilinochchi": (9.3803, 80.3770, "Kilinochchi", "city"),
            "mannar": (8.9810, 79.9044, "Mannar", "city"),
            "point pedro": (9.8241, 80.2362, "Point Pedro", "town"),
            "hambantota": (6.1429, 81.1212, "Hambantota", "city"),
            "kalutara": (6.5854, 79.9607, "Kalutara", "city"),
            "bentota": (6.4259, 79.9997, "Bentota", "town"),
            "hikkaduwa": (6.1408, 80.1030, "Hikkaduwa", "town"),
            "tangalle": (6.0244, 80.7941, "Tangalle", "town"),
            "sigiriya": (7.9570, 80.7603, "Sigiriya", "landmark"),
            "dambulla": (7.8742, 80.6511, "Dambulla", "city"),
            "polonnaruwa": (7.9403, 81.0188, "Polonnaruwa", "city"),
            "puttalam": (8.0362, 79.8283, "Puttalam", "city"),
        }
        for k, v in baseline.items():
            IslandGeocoder._gazetteer[k] = v

        if os.path.exists(places_csv):
            try:
                with open(places_csv, mode="r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get("name", "").strip()
                        if not name:
                            continue
                        geom = row.get("geometry_wkt") or row.get("geometry", "")
                        match = wkt_regex.search(geom)
                        if match:
                            try:
                                lon = float(match.group(1))
                                lat = float(match.group(2))
                                fclass = row.get("fclass", "place")
                                key = name.lower()
                                if key not in IslandGeocoder._gazetteer or fclass in ("city", "town"):
                                    IslandGeocoder._gazetteer[key] = (lat, lon, name, fclass)
                            except (ValueError, IndexError):
                                pass
                logger.info(f"Loaded {len(IslandGeocoder._gazetteer)} places into island gazetteer.")
            except Exception as e:
                logger.warning(f"Error loading {places_csv}: {e}")

    def resolve(self, query: str, allow_network: bool = True, fuzzy: bool = True) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        Resolves any Sri Lanka query to (latitude, longitude, formatted_label).
        Returns (None, None, None) if completely unresolvable.
        """
        if not query:
            return None, None, None

        raw = query.strip()
        lower_q = raw.lower()

        # 1. Decimal coordinates: "6.0367, 80.2170" or "6.0367 80.2170"
        if "," in raw or " " in raw:
            parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
            if len(parts) == 2:
                try:
                    lat_c = float(parts[0])
                    lon_c = float(parts[1])
                    # Validate within Sri Lanka bounding box (lat ~5.5 to 10.0, lon ~79.5 to 82.0)
                    if 5.0 <= lat_c <= 10.5 and 79.0 <= lon_c <= 82.5:
                        return lat_c, lon_c, f"Coord ({lat_c:.4f}, {lon_c:.4f})"
                except ValueError:
                    pass

        # 2. Direct exact match in gazetteer (O(1))
        if lower_q in IslandGeocoder._gazetteer:
            lat, lon, label, _ = IslandGeocoder._gazetteer[lower_q]
            return lat, lon, label

        # 3. Normalized match (e.g. "jaffna city" -> "jaffna", "kandy town" -> "kandy") (O(1))
        cleaned = re.sub(r"\b(city|town|station|fort|junction|bus stand|bus stop)\b", "", lower_q).strip()
        if cleaned in IslandGeocoder._gazetteer:
            lat, lon, label, _ = IslandGeocoder._gazetteer[cleaned]
            return lat, lon, label

        # 4. Prefix / Substring match in gazetteer (only if fuzzy=True)
        if fuzzy:
            for k, (lat, lon, label, fclass) in IslandGeocoder._gazetteer.items():
                if len(k) >= 3 and (k.startswith(cleaned) or cleaned.startswith(k)):
                    return lat, lon, label

        if not allow_network:
            return None, None, None

        # 5. Dynamic OpenStreetMap Nominatim geocoding fallback
        try:
            url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "WandarayaRoutingEngine/1.0 (admin@wandaraya.lk)"}
            params = {
                "q": f"{raw}, Sri Lanka",
                "format": "json",
                "limit": 1,
                "countrycodes": "lk"
            }
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        lat = float(data[0]["lat"])
                        lon = float(data[0]["lon"])
                        display = data[0].get("display_name", raw).split(",")[0]
                        # Cache for subsequent queries
                        IslandGeocoder._gazetteer[lower_q] = (lat, lon, display, "geocoded")
                        return lat, lon, display
        except Exception as e:
            logger.debug(f"Nominatim geocode fallback failed for '{query}': {e}")

        return None, None, None

geocoder = IslandGeocoder.get_instance()
