import unittest
from app.services.graph import GraphMode, Node, Edge, MultimodalGraph

class TestGraphModel(unittest.TestCase):
    def setUp(self):
        self.graph = MultimodalGraph()
        
    def test_add_nodes(self):
        n1 = Node("n1", lat=6.927, lon=79.861)
        self.graph.add_node(n1)
        self.assertIn("n1", self.graph.nodes)
        self.assertEqual(self.graph.get_node("n1").lat, 6.927)

    def test_add_edge_directed(self):
        self.graph.add_node(Node("n1"))
        self.graph.add_node(Node("n2"))
        e = Edge("n1", "n2", GraphMode.ROAD, directed=True, attributes={"distance_km": 1.5})
        self.graph.add_edge(e)
        
        edges_n1_n2 = self.graph.get_edges("n1", "n2")
        self.assertEqual(len(edges_n1_n2), 1)
        self.assertEqual(edges_n1_n2[0].mode, GraphMode.ROAD)
        
        edges_n2_n1 = self.graph.get_edges("n2", "n1")
        self.assertEqual(len(edges_n2_n1), 0)

    def test_add_edge_undirected(self):
        self.graph.add_node(Node("n1"))
        self.graph.add_node(Node("n2"))
        e = Edge("n1", "n2", GraphMode.WALKING, directed=False)
        self.graph.add_edge(e)
        
        self.assertEqual(len(self.graph.get_edges("n1", "n2")), 1)
        self.assertEqual(len(self.graph.get_edges("n2", "n1")), 1)

    def test_add_edge_missing_node(self):
        e = Edge("n1", "n2", GraphMode.BUS)
        with self.assertRaises(ValueError):
            self.graph.add_edge(e)

    def test_graph_statistics(self):
        self.graph.add_node(Node("A"))
        self.graph.add_node(Node("B"))
        self.graph.add_edge(Edge("A", "B", GraphMode.ROAD))
        self.graph.add_edge(Edge("B", "A", GraphMode.ROAD))
        self.graph.add_edge(Edge("A", "B", GraphMode.BUS))
        
        stats = self.graph.get_statistics()
        self.assertEqual(stats["total_nodes"], 2)
        self.assertEqual(stats["edges_by_mode"][GraphMode.ROAD], 2)
        self.assertEqual(stats["edges_by_mode"][GraphMode.BUS], 1)
        self.assertEqual(stats["edges_by_mode"][GraphMode.RAIL], 0)

if __name__ == "__main__":
    unittest.main()
