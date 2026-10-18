import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.transport import TrainStation
from app.services.graph import MultimodalGraph, Node

logger = logging.getLogger(__name__)

class StationGraphLoader:
    def __init__(self, session: AsyncSession, graph: MultimodalGraph):
        self.session = session
        self.graph = graph

    async def load(self) -> int:
        """
        Loads train stations as nodes into the multimodal graph.
        Does not load edges since schedule/sequence data is absent.
        Returns the number of station nodes loaded.
        """
        try:
            result = await self.session.execute(select(TrainStation))
            stations = result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to query train_stations table: {e}")
            return 0
            
        loaded_nodes = 0
        for st in stations:
            if st.lat is None or st.lon is None:
                continue
                
            n_id = f"station_{st.id}"
            
            self.graph.add_node(Node(
                node_id=n_id, 
                lat=st.lat, 
                lon=st.lon,
                properties={
                    "name": st.name,
                    "osm_id": st.osm_id,
                    "type": st.type
                }
            ))
            loaded_nodes += 1
                
        logger.info(f"Loaded {loaded_nodes} train station nodes into the graph.")
        return loaded_nodes
