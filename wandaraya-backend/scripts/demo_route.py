import sys
import asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
from app.database import AsyncSessionLocal
from app.services.graph_builder import graph_builder
from app.services.dijkstra import DijkstraRouter

# Suppress debug logs for cleaner output
logging.getLogger("app.services").setLevel(logging.WARNING)

async def run_live_test():
    print("====== WANDARAYA GRAPH VALIDATION ======")
    print("Starting session and connecting to local database...\n")
    
    try:
        async with AsyncSessionLocal() as session:
            # 1. Build Graph from actual DB records
            print("1. Loading unified Multimodal Graph from database (Roads & Stations)...")
            graph = await graph_builder.build(session, force_reload=True)
            
            stats = graph.get_statistics()
            print("\n--- REAL GRAPH STATISTICS ---")
            print(f"Total Graph Nodes : {stats['total_nodes']}")
            for mode, count in stats["edges_by_mode"].items():
                if count > 0:
                    print(f"Total Edges (Mode: {mode.value.upper()}) : {count}")
                    
            if stats['total_nodes'] < 2:
                print("\n[!] Not enough data directly loaded in DB. Cannot test routing.")
                print("Make sure you imported the Component 2 data via scripts/import_component2_data.py first.")
                return
                
            # 2. Test Dijkstra Router logic
            print("\n2. Initializing Dijkstra Router...")
            router = DijkstraRouter(graph)
            
            # Select random origin and destination from loaded properties
            nodes = list(graph.nodes.keys())
            origin_node = nodes[0]
            dest_node = nodes[-1]
            
            print(f"Attempting Shortest-Path Route:")
            print(f"  Origin: '{origin_node}'")
            print(f"  Destination: '{dest_node}'")
            
            try:
                path, total_distance = router.route(origin_node, dest_node)
                print(f"\n✅ ROUTE SUCCESSFULLY FOUND!")
                print(f"   -> Total Distance : {total_distance:.2f} km")
                print(f"   -> Total Steps (Nodes crossed) : {len(path)}")
                
                print(f"\nSample of Route Path Sequence:")
                for step in path[:5]:
                    print(f"   * {step}")
                if len(path) > 5:
                    print(f"   * ... and {len(path)-5} more nodes.")
                    
            except ValueError as e:
                print(f"\n❌ ROUTING ERROR: {e}")
                print(" (This can natively happen if origin/destination lie in disjoint sub-graphs isolated from each other)")

    except Exception as e:
        print(f"\n[ERROR] Database connection failed or encountered fatal exception:\n -> {e}")
        print("\nPlease ensure your local database container is actively running!")

if __name__ == '__main__':
    asyncio.run(run_live_test())
