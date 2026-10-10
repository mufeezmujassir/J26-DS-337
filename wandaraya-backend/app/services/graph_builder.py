import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.graph import MultimodalGraph
from app.services.road_graph_loader import RoadGraphLoader
from app.services.station_loader import StationGraphLoader
from app.services.transfer_loader import build_transfers

logger = logging.getLogger(__name__)

class MultimodalGraphBuilder:
    def __init__(self):
        self._graph = None

    async def build(self, session: AsyncSession, force_reload: bool = False) -> MultimodalGraph:
        """
        Builds the unified multimodal graph and returns it.
        Uses in-memory caching to avoid rebuilding unless force_reload is True.
        """
        if self._graph is not None and not force_reload:
            logger.info("Returning cached multimodal graph")
            return self._graph

        logger.info("Building unified multimodal graph...")
        graph = MultimodalGraph()

        # Load road network core
        road_loader = RoadGraphLoader(session, graph)
        await road_loader.load()

        # Load railway nodes
        station_loader = StationGraphLoader(session, graph)
        await station_loader.load()
        
        # Build logical intermodal transfers using proximity
        build_transfers(graph, max_walk_km=1.0)
        
        stats = graph.get_statistics()
        logger.info(f"Graph successfully built. Stats: {stats}")
        
        self._graph = graph
        return graph

# Global singleton builder instance for application lifespan
graph_builder = MultimodalGraphBuilder()
