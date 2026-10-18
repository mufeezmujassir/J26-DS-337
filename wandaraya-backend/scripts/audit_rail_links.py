import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.graph import MultimodalGraph
from app.services.rail_graph_loader import rail_graph_loader
from app.services.bus_graph_loader import bus_graph_loader
from app.services.transfer_loader import build_transfers
from app.services.dijkstra import DijkstraRouter

print("=== CHECKING RAIL CORRIDORS CONNECTIVITY ===")
g = MultimodalGraph()
rail_edges = rail_graph_loader.load_into_graph(g)
print(f"Total rail edges loaded: {rail_edges}")

for corridor_name, stations in rail_graph_loader.CORRIDORS.items():
    print(f"\nChecking Corridor: {corridor_name} ({len(stations)} stations)")
    for i in range(len(stations) - 1):
        s1 = stations[i]
        s2 = stations[i+1]
        n1 = f"rail_{rail_graph_loader._normalize_name(s1).replace(' ', '_')}"
        n2 = f"rail_{rail_graph_loader._normalize_name(s2).replace(' ', '_')}"
        
        edges = g.get_edges(n1, n2)
        if not edges:
            c1 = rail_graph_loader.station_coords.get(rail_graph_loader._normalize_name(s1))
            c2 = rail_graph_loader.station_coords.get(rail_graph_loader._normalize_name(s2))
            print(f"  [BROKEN] {s1} ({n1}, coord={c1}) -> {s2} ({n2}, coord={c2})")
