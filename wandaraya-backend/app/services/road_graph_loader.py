import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.graph import MultimodalGraph, Node, Edge, GraphMode

logger = logging.getLogger(__name__)

class RoadGraphLoader:
    def __init__(self, session: AsyncSession, graph: MultimodalGraph):
        self.session = session
        self.graph = graph

    async def load(self) -> int:
        """
        Loads road edges into the provided multimodal graph.
        Returns the number of valid road edges loaded.
        """
        query = text("""
            SELECT 
                road_id,
                total_length_km,
                ST_X(ST_StartPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as start_lon,
                ST_Y(ST_StartPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as start_lat,
                ST_X(ST_EndPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as end_lon,
                ST_Y(ST_EndPoint(ST_CurveToLine(ST_LineMerge(geometry)))) as end_lat
            FROM roads
            WHERE geometry IS NOT NULL
        """)
        
        try:
            result = await self.session.execute(query)
            rows = result.fetchall()
        except Exception as e:
            logger.error(f"Failed to query roads table: {e}")
            return 0
            
        loaded_edges = 0
        for row in rows:
            r_id, length, slon, slat, elon, elat = row
            
            if slon is None or slat is None or elon is None or elat is None:
                continue
                
            weight = length if length is not None else 0.0
            
            n1_id = f"road_{slon}_{slat}"
            n2_id = f"road_{elon}_{elat}"
            
            # Use dictionary keys to prevent duplicates, though add_node is idempotent usually
            self.graph.add_node(Node(node_id=n1_id, lat=slat, lon=slon))
            self.graph.add_node(Node(node_id=n2_id, lat=elat, lon=elon))
            
            edge = Edge(
                from_node=n1_id,
                to_node=n2_id,
                mode=GraphMode.ROAD,
                directed=False,
                attributes={"distance_km": float(weight), "source_id": str(r_id)}
            )
            
            try:
                self.graph.add_edge(edge)
                loaded_edges += 1
            except ValueError as e:
                logger.warning(f"Error adding road edge {r_id}: {e}")
                
        logger.info(f"Loaded {loaded_edges} road edges into the graph.")
        return loaded_edges
