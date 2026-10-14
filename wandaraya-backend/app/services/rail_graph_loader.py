import os
import logging
import pandas as pd
from typing import Dict, Tuple, Optional, List
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode

logger = logging.getLogger(__name__)

class RailGraphLoader:
    """
    Constructs the Sri Lanka railway network with accurate coordinates and
    official Sri Lanka Railways passenger fares (1st, 2nd, 3rd Class).
    """

    CORRIDORS = {
        "coastal": [
            "Colombo Fort", "Kollupitiya", "Bambalapitiya", "Wellawatta", "Dehiwala",
            "Mount Lavinia", "Moratuwa", "Panadura", "Wadduwa", "Kalutara North",
            "Kalutara South", "Payagala South", "Beruwala", "Aluthgama", "Bentota",
            "Induruwa", "Kosgoda", "Ahungalla", "Balapitiya", "Ambalangoda",
            "Akurala", "Hikkaduwa", "Dodanduwa", "Gintota", "Galle",
            "Talpe", "Koggala", "Ahangama", "Weligama", "Mirissa",
            "Kamburugamuwa", "Matara", "Beliatta"
        ],
        "main_hill_country": [
            "Colombo Fort", "Maradana", "Dematagoda", "Kelaniya", "Ragama",
            "Gampaha", "Veyangoda", "Mirigama", "Ambepussa", "Alawwa",
            "Polgahawela", "Rambukkana", "Kadugannawa", "Pilimatalawa", "Peradeniya Jnc",
            "Kandy", "Gampola", "Nawalapitiya", "Watawala", "Hatton",
            "Kotagala", "Thalawakele", "Watagoda", "Great Western", "Radella",
            "Nanu Oya", "Ambewela", "Pattipola", "Ohiya", "Idalgashinna",
            "Haputale", "Diyatalawa", "Bandarawela", "Ella", "Demodara",
            "Hali Ela", "Badulla"
        ],
        "northern": [
            "Polgahawela", "Pothuhera", "Kurunegala", "Wellawa", "Ganewatta",
            "Maho Jnc", "Ambanpola", "Galgamuwa", "Thambuttegama", "Talawa",
            "Anuradhapura", "Mihintale Jnc", "Medawachchiya Jnc", "Punewa", "Vavuniya",
            "Omanthai", "Puliyankulama", "Mankulam", "Murikandy", "Kilinochchi",
            "Paranthan", "Elephant Pass", "Palai", "Kodikamam", "Chavakachcheri",
            "Navatkuli", "Jaffna", "Kondavil", "Inuvil", "Chunnakam",
            "Mallakam", "Tellipalai", "Kankesanthurai"
        ],
        "eastern_batticaloa": [
            "Maho Jnc", "Kalawewa", "Kekirawa", "Habarana", "Galoya Jnc",
            "Hingurakgoda", "Polonnaruwa", "Manampitiya", "Welikanda", "Punani",
            "Valachchenai", "Kalkuda", "Eravur", "Batticaloa"
        ],
        "eastern_trincomalee": [
            "Galoya Jnc", "Aluthoya", "Kantale", "Thambalagamuwa", "China Bay",
            "Trincomalee"
        ],
        "puttalam": [
            "Ragama", "Ja-Ela", "Seeduwa", "Katunayake", "Negombo",
            "Kochchikade", "Lunuwila", "Nattandiya", "Madampe", "Chilaw",
            "Bangadeniya", "Battulu Oya", "Mundalama", "Palavi", "Puttalam"
        ],
        "mannar": [
            "Medawachchiya Jnc", "Neriyakulam", "Madu Road", "Murunkan", "Mannar",
            "Pesalai", "Thalaimannar", "Talaimannar Pier"
        ],
        "kelani_valley": [
            "Colombo Fort", "Maradana", "Baseline Road", "Cotta Road", "Narahenpita",
            "Kirulapana", "Nugegoda", "Maharagama", "Pannipitiya", "Kottawa",
            "Homagama", "Padukka", "Waga", "Kosgama", "Avissawella"
        ]
    }

    # Speeds by line topology (accounting for elevation, curves, and track limits)
    CORRIDOR_SPEEDS_KMH = {
        "coastal": 50.0,
        "main_hill_country": 35.0,
        "northern": 65.0,
        "eastern_batticaloa": 50.0,
        "eastern_trincomalee": 50.0,
        "puttalam": 48.0,
        "mannar": 45.0,
        "kelani_valley": 30.0
    }

    STATION_ALIASES = {
        "katutara": "kalutara",
        "katutara north": "kalutara north",
        "katutara south": "kalutara south",
        "negambo": "negombo",
        "pilimathalawa": "pilimatalawa",
        "navalapitiya": "nawalapitiya",
        "diyathalawa": "diyatalawa",
        "omanthei": "omanthai",
        "murukandi": "murikandy",
        "murukandy": "murikandy",
        "eliphant pass": "elephant pass",
        "chawakachcheri": "chavakachcheri",
        "thellipalai": "tellipalai",
        "kankasnthurai": "kankesanthurai",
        "walachchena": "valachchenai",
        "baticaloa": "batticaloa",
        "naththandiya": "nattandiya",
        "baththuluoya": "battulu oya",
        "murukkan": "murunkan",
        "vavniya": "vavuniya",
        "tricomalee": "trincomalee",
        "nanuoya": "nanu oya",
        "secretarial": "secretariat",
        "baselin road": "baseline road",
        "peradeniya jnc": "peradeniya",
        "maho jnc": "maho",
        "galoya jnc": "galoya",
        "medawachchiya jnc": "medawachchiya",
        "mihintale jnc": "mihintale",
    }

    def __init__(self, price_csv_path: Optional[str] = None, stations_csv_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.price_csv = price_csv_path or os.path.join(base_dir, "data", "train_data", "train_price.csv")
        self.stations_csv = stations_csv_path or os.path.join(base_dir, "data", "train_data", "sri_lanka_stations_Railway.csv")
        
        self.station_prices: Dict[str, Dict[str, float]] = {}
        self.station_coords: Dict[str, Tuple[float, float]] = {}
        self.distance_tariffs: List[Tuple[float, float, float, float]] = []
        self._load_datasets()

    def _normalize_name(self, name: str) -> str:
        s = name.strip().lower()
        replacements = [
            (" railway station", ""), (" station", ""), (" halt", ""),
            (" jnc", ""), (" junction", ""), (" - ", "-"), ("'", "")
        ]
        for old, new in replacements:
            s = s.replace(old, new)
        s = s.strip()
        return self.STATION_ALIASES.get(s, s)

    def _load_datasets(self):
        # 1. Load coordinates from sri_lanka_stations_Railway.csv
        if os.path.exists(self.stations_csv):
            try:
                df_st = pd.read_csv(self.stations_csv)
                for _, row in df_st.iterrows():
                    st_name = str(row.get("name_en") or row.get("name") or "").strip()
                    lat = row.get("lat")
                    lon = row.get("lon")
                    if st_name and pd.notna(lat) and pd.notna(lon):
                        norm = self._normalize_name(st_name)
                        self.station_coords[norm] = (float(lat), float(lon))
            except Exception as e:
                logger.warning(f"Failed to load railway stations CSV: {e}")

        # Add fallback coordinates for all standard hubs and junctions
        fallback_coords = {
            "colombo fort": (6.9334, 79.8501), "maradana": (6.9272, 79.8653),
            "kalutara north": (6.6012, 79.9543), "kalutara south": (6.5841, 79.9588),
            "kandy": (7.2917, 80.6322), "peradeniya": (7.2680, 80.5960),
            "pilimatalawa": (7.2667, 80.5526), "nawalapitiya": (7.0572, 80.5351),
            "nanu oya": (6.9420, 80.7437), "hatton": (6.8932, 80.5979),
            "diyatalawa": (6.8020, 80.9592), "bandarawela": (6.8290, 80.9876),
            "ella": (6.8718, 81.0469), "demodara": (6.9038, 81.0633),
            "hali ela": (6.9536, 81.0315), "badulla": (6.9934, 81.0550),
            "galle": (6.0348, 80.2142), "matara": (5.9472, 80.5353),
            "beliatta": (6.0465, 80.6865),
            "anuradhapura": (8.3114, 80.4037), "vavuniya": (8.7514, 80.4971),
            "omanthai": (8.8653, 80.5011), "murikandy": (9.2712, 80.4025),
            "kilinochchi": (9.3803, 80.3983), "elephant pass": (9.5024, 80.4059),
            "chavakachcheri": (9.6571, 80.1585), "jaffna": (9.6644, 80.0167),
            "tellipalai": (9.7850, 80.0353), "kankesanthurai": (9.8142, 80.0383),
            "polonnaruwa": (7.9403, 81.0188), "valachchenai": (7.9255, 81.5303),
            "batticaloa": (7.7247, 81.6989), "aluthoya": (8.2250, 80.9167),
            "trincomalee": (8.5874, 81.2152), "kurunegala": (7.4818, 80.3609),
            "polgahawela": (7.3307, 80.3012), "maho": (7.8171, 80.2798),
            "negombo": (7.2103, 79.8420), "nattandiya": (7.4143, 79.8661),
            "battulu oya": (7.7272, 79.8317), "puttalam": (8.0336, 79.8283),
            "madu road": (8.7738, 80.1573), "murunkan": (8.8358, 80.0242),
            "mannar": (8.9758, 79.9171), "thalaimannar": (9.1065, 79.7289),
            "avissawella": (6.9536, 80.2106)
        }
        for k, v in fallback_coords.items():
            if k not in self.station_coords:
                self.station_coords[k] = v

        # Dynamic geocoder fallback for any corridor stations
        from app.services.island_geocoder import geocoder
        for corridor_stations in self.CORRIDORS.values():
            for st in corridor_stations:
                st_norm = self._normalize_name(st)
                if st_norm not in self.station_coords:
                    lat, lon, _ = geocoder.resolve(st, allow_network=False, fuzzy=True)
                    if lat is not None and lon is not None:
                        self.station_coords[st_norm] = (lat, lon)

        # 2. Load official ticket prices from train_price.csv
        if os.path.exists(self.price_csv):
            try:
                df_p = pd.read_csv(self.price_csv).sort_values("Distance_Km")
                for _, row in df_p.iterrows():
                    st_name = str(row.get("Station", "")).strip()
                    if not st_name:
                        continue
                    norm = self._normalize_name(st_name)
                    dist = float(row.get("Distance_Km", 0.0))
                    c1 = float(row.get("1st_Class_Rs", 0.0))
                    c2 = float(row.get("2nd_Class_Rs", 0.0))
                    c3 = float(row.get("3rd_Class_Rs", 0.0))
                    self.station_prices[norm] = {
                        "name": st_name,
                        "distance_km": dist,
                        "1st_class_rs": c1,
                        "2nd_class_rs": c2,
                        "3rd_class_rs": c3
                    }
                    self.distance_tariffs.append((dist, c3, c2, c1))
            except Exception as e:
                logger.warning(f"Failed to load train prices CSV: {e}")

    def lookup_distance_tariff(self, distance_km: float) -> Dict[str, float]:
        """
        Looks up the official Gazette passenger fare for a given rail track distance.
        """
        if distance_km <= 0.0:
            return {"distance_km": 0.0, "3rd_class_rs": 20.0, "2nd_class_rs": 50.0, "1st_class_rs": 100.0}

        # Find closest stage tariff >= distance_km
        for dist, c3, c2, c1 in self.distance_tariffs:
            if dist >= distance_km:
                return {
                    "distance_km": round(distance_km, 2),
                    "3rd_class_rs": round(max(20.0, c3), 2),
                    "2nd_class_rs": round(max(50.0, c2), 2),
                    "1st_class_rs": round(max(100.0, c1), 2)
                }

        # If beyond maximum tabulated distance, scale with maximum distance stage rate
        if self.distance_tariffs:
            max_dist, mc3, mc2, mc1 = self.distance_tariffs[-1]
            scale = max(1.0, distance_km / max(1.0, max_dist))
            return {
                "distance_km": round(distance_km, 2),
                "3rd_class_rs": round(mc3 * scale, 2),
                "2nd_class_rs": round(mc2 * scale, 2),
                "1st_class_rs": round(mc1 * scale, 2)
            }

        return {
            "distance_km": round(distance_km, 2),
            "3rd_class_rs": round(max(20.0, distance_km * 1.5), 2),
            "2nd_class_rs": round(max(50.0, distance_km * 3.0), 2),
            "1st_class_rs": round(max(100.0, distance_km * 5.8), 2)
        }

    def get_fare(self, from_station: str, to_station: str) -> Dict[str, float]:
        """
        Calculates official Sri Lanka Railways fare between any two stations.
        If stations are found in the official Gazette dataset, accurately looks up
        the gazetted distance stage tariff.
        """
        f_norm = self._normalize_name(from_station)
        t_norm = self._normalize_name(to_station)

        p1 = self.station_prices.get(f_norm)
        p2 = self.station_prices.get(t_norm)

        if p1 and p2:
            dist_diff = abs(p2["distance_km"] - p1["distance_km"])
            if dist_diff <= 0.0:
                dist_diff = 1.0

            # Direct lookup if one of the stations is Colombo Fort (terminal station 0.00 km)
            if p1["distance_km"] == 0.0:
                return {
                    "distance_km": round(p2["distance_km"], 2),
                    "3rd_class_rs": round(p2["3rd_class_rs"], 2),
                    "2nd_class_rs": round(p2["2nd_class_rs"], 2),
                    "1st_class_rs": round(p2["1st_class_rs"], 2)
                }
            elif p2["distance_km"] == 0.0:
                return {
                    "distance_km": round(p1["distance_km"], 2),
                    "3rd_class_rs": round(p1["3rd_class_rs"], 2),
                    "2nd_class_rs": round(p1["2nd_class_rs"], 2),
                    "1st_class_rs": round(p1["1st_class_rs"], 2)
                }

            # For intermediate journeys, lookup official Gazette distance stage tariff
            tariff = self.lookup_distance_tariff(dist_diff)
            return tariff

        # Fallback if station name isn't matched: resolve coordinates or distance
        c1 = self.station_coords.get(f_norm)
        c2 = self.station_coords.get(t_norm)
        if c1 and c2:
            from app.services.spatial import haversine_km
            approx_dist = haversine_km(c1[0], c1[1], c2[0], c2[1]) * 1.18
            return self.lookup_distance_tariff(approx_dist)

        return {
            "distance_km": 0.0,
            "3rd_class_rs": 240.0,
            "2nd_class_rs": 500.0,
            "1st_class_rs": 950.0
        }

    def load_into_graph(self, graph: MultimodalGraph) -> int:
        """
        Builds all railway lines into the MultimodalGraph.
        """
        edges_added = 0
        added_nodes = set()

        for corridor_name, stations in self.CORRIDORS.items():
            speed_kmh = self.CORRIDOR_SPEEDS_KMH.get(corridor_name, 50.0)

            for i in range(len(stations) - 1):
                s1_raw = stations[i]
                s2_raw = stations[i+1]

                s1_norm = self._normalize_name(s1_raw)
                s2_norm = self._normalize_name(s2_raw)

                coord1 = self.station_coords.get(s1_norm)
                coord2 = self.station_coords.get(s2_norm)

                if not coord1 or not coord2:
                    continue

                node1_id = f"rail_{s1_norm.replace(' ', '_')}"
                node2_id = f"rail_{s2_norm.replace(' ', '_')}"

                if node1_id not in added_nodes and node1_id not in graph.nodes:
                    graph.add_node(Node(
                        node1_id, lat=coord1[0], lon=coord1[1],
                        properties={"name": f"{s1_raw} Railway Station", "mode": "rail"}
                    ))
                    added_nodes.add(node1_id)

                if node2_id not in added_nodes and node2_id not in graph.nodes:
                    graph.add_node(Node(
                        node2_id, lat=coord2[0], lon=coord2[1],
                        properties={"name": f"{s2_raw} Railway Station", "mode": "rail"}
                    ))
                    added_nodes.add(node2_id)

                # Determine distance and fare between adjacent stations
                fare_info = self.get_fare(s1_raw, s2_raw)
                dist_km = fare_info["distance_km"]
                if dist_km <= 0.0:
                    # Calculate haversine distance
                    from app.services.transfer_loader import haversine
                    dist_km = round(haversine(coord1[0], coord1[1], coord2[0], coord2[1]) * 1.15, 2)

                time_min = round((dist_km / speed_kmh) * 60.0, 1)
                cost_lkr = round(dist_km * 1.8, 2)

                edge = Edge(
                    from_node=node1_id,
                    to_node=node2_id,
                    mode=GraphMode.RAIL,
                    directed=False,
                    attributes={
                        "distance_km": float(dist_km),
                        "travel_time_min": float(time_min),
                        "cost_lkr": float(cost_lkr),
                        "fare_1st_rs": float(fare_info["1st_class_rs"]),
                        "fare_2nd_rs": float(fare_info["2nd_class_rs"]),
                        "fare_3rd_rs": float(cost_lkr),
                        "corridor": corridor_name,
                        "line_name": f"{corridor_name.title()} Railway Line",
                        "waiting_time_min": 10.0,
                        "source_dataset": "sri_lanka_railway_train_price"
                    }
                )
                try:
                    graph.add_edge(edge)
                    edges_added += 1
                except ValueError:
                    pass

        logger.info(f"Loaded {edges_added} railway edges across {len(self.CORRIDORS)} corridors.")
        return edges_added

rail_graph_loader = RailGraphLoader()
