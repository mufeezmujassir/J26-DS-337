import sys, os
backend_dir = os.path.abspath('wandaraya-backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from scripts.run_swagger import get_graph, parse_location, find_transit_access
from app.services.graph import Node, Edge, GraphMode
from app.services.dijkstra import DijkstraRouter
from app.services.scenic_service import scenic_service

graph = get_graph()

test_corridors = [
    ("Colombo", "Galle"),
    ("Colombo", "Kandy"),
    ("Colombo", "Badulla"),
    ("Colombo", "Matara"),
    ("Colombo", "Jaffna"),
    ("Kandy", "Ella"),
    ("Batticaloa", "Ampara"),
    ("Ampara", "Hambantota")
]

print("=" * 80)
print("     WANDARAYA: 5-OBJECTIVE MULTIMODAL ROUTING VERIFICATION AUDIT")
print("=" * 80)

for start_name, end_name in test_corridors:
    s_lat, s_lon, s_lbl = parse_location(start_name)
    e_lat, e_lon, e_lbl = parse_location(end_name)

    v_start = f"audit_start_{start_name}"
    v_end = f"audit_end_{end_name}"

    # Clean previous
    for v in [v_start, v_end]:
        if v in graph.nodes: del graph.nodes[v]
        if v in graph.edges: del graph.edges[v]

    graph.add_node(Node(v_start, lat=s_lat, lon=s_lon, properties={"label": start_name}))
    graph.add_node(Node(v_end, lat=e_lat, lon=e_lon, properties={"label": end_name}))

    s_nodes = find_transit_access(s_lat, s_lon, graph)
    e_nodes = find_transit_access(e_lat, e_lon, graph)

    for mode in ["rail", "bus"]:
        st, sd = s_nodes[mode]
        if st and sd <= 35.0:
            graph.add_edge(Edge(v_start, st, GraphMode.WALKING, True, {"distance_km": sd, "travel_time_min": (sd/4.5)*60, "cost_lkr": 0.0}))
            graph.add_edge(Edge(st, v_start, GraphMode.WALKING, True, {"distance_km": sd, "travel_time_min": (sd/4.5)*60, "cost_lkr": 0.0}))
        et, ed = e_nodes[mode]
        if et and ed <= 35.0:
            graph.add_edge(Edge(et, v_end, GraphMode.WALKING, True, {"distance_km": ed, "travel_time_min": (ed/4.5)*60, "cost_lkr": 0.0}))
            graph.add_edge(Edge(v_end, et, GraphMode.WALKING, True, {"distance_km": ed, "travel_time_min": (ed/4.5)*60, "cost_lkr": 0.0}))

    # Fallback nearest bus
    sb, sbd = s_nodes["bus"]
    if sb and (v_start not in graph.edges or not graph.edges[v_start]):
        graph.add_edge(Edge(v_start, sb, GraphMode.WALKING, True, {"distance_km": sbd, "travel_time_min": (sbd/4.5)*60, "cost_lkr": 0.0}))
        graph.add_edge(Edge(sb, v_start, GraphMode.WALKING, True, {"distance_km": sbd, "travel_time_min": (sbd/4.5)*60, "cost_lkr": 0.0}))
    eb, ebd = e_nodes["bus"]
    if eb and (v_end not in graph.edges or not graph.edges[v_end]):
        graph.add_edge(Edge(eb, v_end, GraphMode.WALKING, True, {"distance_km": ebd, "travel_time_min": (ebd/4.5)*60, "cost_lkr": 0.0}))
        graph.add_edge(Edge(v_end, eb, GraphMode.WALKING, True, {"distance_km": ebd, "travel_time_min": (ebd/4.5)*60, "cost_lkr": 0.0}))

    print(f"\n[*] CORRIDOR: {start_name} -> {end_name}")
    for obj in ["shortest", "fastest", "cheapest", "slower", "scenic"]:
        router = DijkstraRouter(graph, objective=obj)
        res = router.route(v_start, v_end)
        if res:
            coords = [(graph.get_node(n).lat, graph.get_node(n).lon) for n in res.nodes if graph.get_node(n) and graph.get_node(n).lat is not None]
            scenic = scenic_service.calculate_scenic_score(coords, res.total_distance_km, corridor_radius_km=7.5, objective=obj)
            h = int(res.total_travel_time_min // 60) if res.total_travel_time_min else 0
            m = int(res.total_travel_time_min % 60) if res.total_travel_time_min else 0
            modes = [m.capitalize() for m in res.modes_used if m.lower() != "walking"]
            print(f"    {obj.upper():<9} | Dist: {res.total_distance_km:>6.1f} km | Time: {h}h {m:02d}m ({res.total_travel_time_min:>5.1f} min) | Fare: {res.total_cost_lkr:>6.1f} LKR | Scenic: {scenic['scenic_score']:>2}★ | Modes: {' + '.join(modes)}")
        else:
            print(f"    {obj.upper():<9} | NO ROUTE FOUND")

    # Clean up
    for v in [v_start, v_end]:
        if v in graph.nodes: del graph.nodes[v]
        if v in graph.edges: del graph.edges[v]
        for u in list(graph.edges.keys()):
            if v in graph.edges[u]:
                del graph.edges[u][v]
