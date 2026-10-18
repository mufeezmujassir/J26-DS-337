import os
import csv
import logging
from typing import Dict, Tuple, Optional
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode
from app.services.spatial import haversine_km
from app.services.island_geocoder import geocoder

logger = logging.getLogger(__name__)

class BusGraphLoader:
    """
    Loads bus routes, stages, and fares across Sri Lanka into the MultimodalGraph.
    Integrates real fares from bus_fares_clean.csv and establishes multimodal connectivity.
    """
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
        )

    def load_into_graph(self, graph: MultimodalGraph) -> int:
        """
        Loads all-island bus network routes and fares into the graph.
        Returns the number of bus edges loaded.
        """
        bus_csv = os.path.join(self.data_dir, "bus_data", "bus_fares_clean.csv")
        if not os.path.exists(bus_csv):
            logger.warning(f"Bus fares CSV not found at {bus_csv}")
            return 0

        # Primary all-island trunk bus corridors across Sri Lanka
        # Route No, From, To, distance_km, travel_time_min, fare_lkr, via
        trunk_bus_corridors = [
            ("BUS 87", "colombo", "jaffna", 396.0, 480.0, 1150.0, "Vavuniya, Kilinochchi"),
            ("BUS 87", "anuradhapura", "jaffna", 195.0, 240.0, 620.0, "Medawachchiya, Vavuniya"),
            ("BUS 87", "vavuniya", "jaffna", 145.0, 180.0, 480.0, "Kilinochchi"),
            ("BUS 87", "kilinochchi", "jaffna", 68.0, 90.0, 240.0, "Elephant Pass"),
            ("BUS 1", "colombo", "kandy", 115.0, 195.0, 385.0, "Waradapola, Kegalle"),
            ("BUS 2", "colombo", "galle", 116.0, 180.0, 390.0, "Kalutara, Aluthgama"),
            ("BUS 2", "galle", "matara", 43.0, 65.0, 160.0, "Ahangama, Weligama"),
            ("BUS 2", "colombo", "matara", 160.0, 240.0, 550.0, "Galle Road Regulated Stage"),
            ("BUS EX 1", "colombo", "galle", 118.0, 90.0, 650.0, "Southern Expressway"),
            ("BUS EX 1", "galle", "matara", 45.0, 35.0, 250.0, "Southern Expressway"),
            ("BUS EX 1", "colombo", "matara", 160.0, 120.0, 900.0, "Southern Expressway (Direct Makumbura - Matara)"),
            ("BUS 49", "colombo", "trincomalee", 260.0, 360.0, 890.0, "Kurunegala, Dambulla"),
            ("BUS 48", "colombo", "batticaloa", 310.0, 420.0, 1050.0, "Polonnaruwa"),
            ("BUS 99", "colombo", "badulla", 225.0, 360.0, 820.0, "Ratnapura, Balangoda"),
            ("BUS 15", "colombo", "anuradhapura", 205.0, 300.0, 680.0, "Kurunegala, Dambulla"),
            ("BUS 6", "colombo", "kurunegala", 94.0, 150.0, 310.0, "Ambepussa, Alawwa"),
            ("BUS 43", "kandy", "jaffna", 310.0, 420.0, 980.0, "Dambulla, Vavuniya"),
            ("BUS 47", "kandy", "nuwara eliya", 77.0, 150.0, 310.0, "Gampola, Hatton"),
            ("BUS 10", "nuwara eliya", "badulla", 58.0, 120.0, 240.0, "Welimada"),
            ("BUS 32", "matara", "hambantota", 75.0, 110.0, 290.0, "Tangalle"),
            ("BUS 32", "colombo", "kataragama", 285.0, 390.0, 950.0, "Matara, Hambantota"),
            ("BUS 4", "colombo", "negombo", 38.0, 60.0, 145.0, "Ja-Ela"),
            ("BUS 4", "negombo", "puttalam", 95.0, 140.0, 340.0, "Chilaw"),
            ("BUS 4", "puttalam", "anuradhapura", 74.0, 110.0, 260.0, "Nochchiyagama"),
            ("BUS 4", "puttalam", "mannar", 130.0, 180.0, 450.0, "Silavathurai"),
            ("BUS 754", "jaffna", "point pedro", 34.0, 50.0, 130.0, "Chunnakam, Karaveddy"),
        ]

        loaded_edges = 0

        # Load trunk corridors into graph
        for r_no, from_name, to_name, dist_km, time_min, fare_lkr, via in trunk_bus_corridors:
            lat1, lon1, lbl1 = geocoder.resolve(from_name, allow_network=False)
            lat2, lon2, lbl2 = geocoder.resolve(to_name, allow_network=False)

            if lat1 is not None and lat2 is not None:
                n1_id = f"bus_{from_name.replace(' ', '_')}"
                n2_id = f"bus_{to_name.replace(' ', '_')}"

                graph.add_node(Node(n1_id, lat=lat1, lon=lon1, properties={"name": f"{lbl1} Bus Stand", "mode": "bus"}))
                graph.add_node(Node(n2_id, lat=lat2, lon=lon2, properties={"name": f"{lbl2} Bus Stand", "mode": "bus"}))

                edge = Edge(
                    from_node=n1_id,
                    to_node=n2_id,
                    mode=GraphMode.BUS,
                    directed=False,
                    attributes={
                        "distance_km": float(dist_km),
                        "travel_time_min": float(time_min),
                        "cost_lkr": float(fare_lkr),
                        "route_no": r_no,
                        "via": via,
                        "waiting_time_min": 10.0,
                        "source_dataset": "bus_fares_clean"
                    }
                )
                try:
                    graph.add_edge(edge)
                    loaded_edges += 1
                except ValueError as e:
                    logger.debug(f"Edge add error: {e}")

        # Ingest representative routes from bus_fares_clean.csv
        try:
            with open(bus_csv, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                seen_pairs = set()

                for row in reader:
                    r_no = row.get("Route No", "").strip()
                    f_loc = row.get("From", "").strip().lower()
                    t_loc = row.get("To", "").strip().lower()
                    note = row.get("Note", "")

                    if "suspect" in note or not f_loc or not t_loc or f_loc == t_loc:
                        continue

                    pair_key = (r_no, f_loc, t_loc)
                    if pair_key in seen_pairs:
                        continue

                    try:
                        fare = float(row.get("Fare (LKR)", 0.0))
                    except ValueError:
                        continue

                    # Discard erroneous OCR spikes > 3000 LKR for local routes
                    if fare <= 0.0 or fare > 2500.0:
                        continue

                    lat1, lon1, lbl1 = geocoder.resolve(f_loc, allow_network=False, fuzzy=False)
                    lat2, lon2, lbl2 = geocoder.resolve(t_loc, allow_network=False, fuzzy=False)

                    if lat1 is not None and lat2 is not None:
                        dist_calc = haversine_km(lat1, lon1, lat2, lon2)
                        if dist_calc < 5.0 or dist_calc > 450.0:
                            continue

                        # Discard OCR artifacts where short stage fare was assigned to long-distance terminal pair
                        if dist_calc > 40.0 and fare < (dist_calc * 1.5):
                            continue

                        # Approximate road curvature factor ~ 1.25x haversine
                        road_dist = round(dist_calc * 1.25, 2)
                        travel_time = round((road_dist / 35.0) * 60.0, 1)

                        n1_id = f"bus_{f_loc.replace(' ', '_')}"
                        n2_id = f"bus_{t_loc.replace(' ', '_')}"

                        graph.add_node(Node(n1_id, lat=lat1, lon=lon1, properties={"name": f"{lbl1} Bus Stand"}))
                        graph.add_node(Node(n2_id, lat=lat2, lon=lon2, properties={"name": f"{lbl2} Bus Stand"}))

                        edge = Edge(
                            from_node=n1_id,
                            to_node=n2_id,
                            mode=GraphMode.BUS,
                            directed=False,
                            attributes={
                                "distance_km": road_dist,
                                "travel_time_min": travel_time,
                                "cost_lkr": fare,
                                "route_no": f"BUS {r_no}",
                                "waiting_time_min": 10.0,
                                "source_dataset": "bus_fares_clean"
                            }
                        )
                        try:
                            graph.add_edge(edge)
                            loaded_edges += 1
                            seen_pairs.add(pair_key)
                        except ValueError:
                            pass

                        if loaded_edges >= 500:
                            break
        except Exception as e:
            logger.warning(f"Error reading {bus_csv}: {e}")

        logger.info(f"Loaded {loaded_edges} bus route edges into graph.")
        return loaded_edges

bus_graph_loader = BusGraphLoader()
