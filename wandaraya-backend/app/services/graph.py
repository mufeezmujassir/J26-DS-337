from enum import Enum
from typing import Dict, Any, List, Optional

class GraphMode(str, Enum):
    ROAD = 'road'
    BUS = 'bus'
    RAIL = 'rail'
    WALKING = 'walking'
    TRANSFER = 'transfer'

class Node:
    def __init__(self, node_id: str, lat: Optional[float] = None, lon: Optional[float] = None, properties: Optional[Dict[str, Any]] = None):
        self.node_id = node_id
        self.lat = lat
        self.lon = lon
        self.properties = properties or {}

    def __repr__(self):
        return f"Node(id={self.node_id}, properties={self.properties})"

class Edge:
    def __init__(self, from_node: str, to_node: str, mode: GraphMode, directed: bool = True, attributes: Optional[Dict[str, Any]] = None):
        self.from_node = from_node
        self.to_node = to_node
        self.mode = mode
        self.directed = directed
        default_attrs = {
            "distance_km": None,
            "travel_time_min": None,
            "cost_lkr": None,
            "source_id": None,
            "source_dataset": None,
            "transfer_type": None,
            "is_estimated": False
        }
        self.attributes = {**default_attrs, **(attributes or {})}

    def __repr__(self):
        return f"Edge({self.from_node} -> {self.to_node}, mode={self.mode}, directed={self.directed})"

class MultimodalGraph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        # Adjacency list: from_node_id -> Dict of to_node_id -> List of Edges 
        # (multigraph capability since there can be multiple modes between two nodes)
        self.edges: Dict[str, Dict[str, List[Edge]]] = {}

    def add_node(self, node: Node):
        if node.node_id not in self.nodes:
            self.nodes[node.node_id] = node
            self.edges.setdefault(node.node_id, {})

    def add_edge(self, edge: Edge):
        if edge.from_node not in self.nodes or edge.to_node not in self.nodes:
            raise ValueError(f"Nodes must exist in the graph before adding an edge. Missing {edge.from_node} or {edge.to_node}")
            
        self.edges[edge.from_node].setdefault(edge.to_node, []).append(edge)
        if not edge.directed:
            reversed_edge = Edge(
                from_node=edge.to_node,
                to_node=edge.from_node,
                mode=edge.mode,
                directed=edge.directed,
                attributes=edge.attributes
            )
            self.edges[edge.to_node].setdefault(edge.from_node, []).append(reversed_edge)

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)
        
    def get_edges(self, from_node: str, to_node: str) -> List[Edge]:
        if from_node in self.edges and to_node in self.edges[from_node]:
            return self.edges[from_node][to_node]
        return []

    def get_all_edges_from(self, node_id: str) -> List[Edge]:
        if node_id not in self.edges:
            return []
        all_outgoing = []
        for to_node, edges in self.edges[node_id].items():
            all_outgoing.extend(edges)
        return all_outgoing

    def get_statistics(self) -> Dict[str, Any]:
        node_count = len(self.nodes)
        edge_count_by_mode = {mode: 0 for mode in GraphMode}
        for from_node, to_dict in self.edges.items():
            for to_node, edge_list in to_dict.items():
                for edge in edge_list:
                    edge_count_by_mode[edge.mode] += 1
        
        return {
            "total_nodes": node_count,
            "edges_by_mode": edge_count_by_mode
        }
