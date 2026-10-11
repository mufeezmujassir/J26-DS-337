"""High performance streaming roads importer for WANDARAYA.

Streams 1,279,946 road records from Desktop CSV into PostgreSQL using
psycopg3 COPY streaming, unlogged staging, and PostGIS ST_Multi(ST_GeomFromText).
"""
import os
import sys
import time
from pathlib import Path
import psycopg

CSV_PATH = Path(r"c:\Users\abdul\OneDrive\Desktop\Rsearch\sri_lanka_all_roads_v4_FINAL.csv")
if not CSV_PATH.exists():
    CSV_PATH = Path(r"c:\Users\abdul\OneDrive\Desktop\Rsearch\sri_lanka_all_roads_v4_FINAL (1).csv")

DB_PARAMS = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "root",
    "dbname": "wandaraya",
}

def main():
    print(f"[*] Starting fast road import from: {CSV_PATH}")
    if not CSV_PATH.exists():
        print(f"[!] Error: CSV file not found at {CSV_PATH}")
        sys.exit(1)
        
    start_time = time.time()
    
    print("[*] Connecting to PostgreSQL...")
    with psycopg.connect(**DB_PARAMS, autocommit=True) as conn:
        with conn.cursor() as cur:
            print("[*] Creating UNLOGGED staging table...")
            cur.execute("DROP TABLE IF EXISTS roads_staging;")
            cur.execute("""
                CREATE UNLOGGED TABLE roads_staging (
                    road_id TEXT,
                    road_name TEXT,
                    road_number TEXT,
                    road_class TEXT,
                    geometry_wkt TEXT,
                    length_km TEXT,
                    road_condition TEXT,
                    surface_type TEXT,
                    lanes TEXT,
                    speed_limit TEXT,
                    bridge_id TEXT,
                    traffic_volume TEXT,
                    closure_status TEXT,
                    district TEXT
                );
            """)

            print("[*] Streaming CSV rows directly into staging table (zero disk copy)...")
            stream_start = time.time()
            with open(CSV_PATH, "rb") as f:
                with cur.copy(
                    "COPY roads_staging (road_id, road_name, road_number, road_class, "
                    "geometry_wkt, length_km, road_condition, surface_type, lanes, "
                    "speed_limit, bridge_id, traffic_volume, closure_status, district) "
                    "FROM STDIN WITH (FORMAT csv, HEADER true)"
                ) as copy:
                    bytes_read = 0
                    while chunk := f.read(524288): # 512 KB chunks
                        copy.write(chunk)
                        bytes_read += len(chunk)
                        if bytes_read % (50 * 1024 * 1024) < 524288:
                            print(f"    Streamed {bytes_read / (1024*1024):.1f} MB...")
            print(f"[+] CSV stream complete in {time.time() - stream_start:.2f}s.")

            cur.execute("SELECT count(*) FROM roads_staging;")
            staged_count = cur.fetchone()[0]
            print(f"[+] Total staged records: {staged_count}")

            print("[*] Dropping secondary indexes on roads for fastest insert...")
            cur.execute("DROP INDEX IF EXISTS ix_roads_road_id;")
            cur.execute("DROP INDEX IF EXISTS idx_roads_geometry;")

            print("[*] Truncating roads table...")
            cur.execute("TRUNCATE TABLE roads RESTART IDENTITY;")

            print("[*] Ingesting into roads table with PostGIS ST_Multi(ST_GeomFromText)...")
            insert_start = time.time()
            cur.execute("""
                INSERT INTO roads (
                    road_id, name, road_number, road_class, road_type, road_condition,
                    lanes, speed_limit, bridge_id, traffic_volume, closure_status,
                    total_length_km, district, source, geometry, created_at
                )
                SELECT 
                    road_id,
                    road_name,
                    road_number,
                    road_class,
                    surface_type,
                    road_condition,
                    CASE WHEN lanes ~ '^[0-9]+$' THEN lanes::INTEGER ELSE NULL END,
                    CASE WHEN speed_limit ~ '^[0-9]+(\.[0-9]+)?$' THEN speed_limit::DOUBLE PRECISION ELSE NULL END,
                    bridge_id,
                    traffic_volume,
                    closure_status,
                    CASE WHEN length_km ~ '^[0-9]+(\.[0-9]+)?$' THEN length_km::DOUBLE PRECISION ELSE NULL END,
                    district,
                    'combined_v4',
                    CASE 
                        WHEN geometry_wkt IS NOT NULL AND geometry_wkt != '' 
                        THEN ST_Multi(ST_GeomFromText(geometry_wkt, 4326))
                        ELSE NULL
                    END,
                    NOW()
                FROM roads_staging;
            """)
            print(f"[+] Roads ingested in {time.time() - insert_start:.2f}s.")

            print("[*] Dropping staging table to immediately release disk space...")
            cur.execute("DROP TABLE roads_staging;")

            print("[*] Recreating spatial and ID indexes...")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_roads_road_id ON roads(road_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_roads_geometry ON roads USING GIST(geometry);")

            print("[*] Running ANALYZE on roads table...")
            cur.execute("ANALYZE roads;")

            print("[*] Verifying final table counts...")
            cur.execute("SELECT count(*), count(geometry) FROM roads;")
            total_rows, total_geoms = cur.fetchone()
            print("=" * 60)
            print(f"[SUCCESS] Total Rows in 'roads' Table   : {total_rows:,}")
            print(f"[SUCCESS] Rows with Valid Geometry       : {total_geoms:,}")
            print(f"[SUCCESS] Total Elapsed Time             : {time.time() - start_time:.2f}s")
            print("=" * 60)

if __name__ == "__main__":
    main()
