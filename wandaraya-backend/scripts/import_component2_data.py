"""Component 2 import pipeline - step 1: roads.

Validation command:
  python scripts/import_component2_data.py --roads --validate

Import command:
  python scripts/import_component2_data.py --roads
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import datetime
from pathlib import Path

from geoalchemy2 import WKTElement

try:
    from app.database import AsyncSessionLocal
    from app.models import Road
    from app.models.transport import BusFare, TrainStation, TrainFare
except Exception:
    AsyncSessionLocal = None
    Road = None
    BusFare = None
    TrainStation = None
    TrainFare = None

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


def _header_map(header_row):
    return {h.strip().lower(): i for i, h in enumerate(header_row)}


def _open_csv(path: Path):
    try:
        try:
            csv.field_size_limit(sys.maxsize)
        except OverflowError:
            csv.field_size_limit(2147483647)
        fh = path.open(newline='', encoding='utf-8')
        reader = csv.reader(fh)
        header = next(reader)
        return reader, _header_map(header), fh
    except Exception as exc:
        print(f"failed to read CSV {path}: {exc}")
        return None, None, None


async def _with_session(func, *, validate: bool = False):
    if AsyncSessionLocal is None:
        print("AsyncSessionLocal not available; skipping DB write operations.")
        return await func(None, validate=validate)
    async with AsyncSessionLocal() as session:
        return await func(session, validate=validate)


async def import_roads(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "road_route" / "rda_national_roads.csv"
    if not path.exists():
        print(f"roads file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        total += 1
        if validate and i <= 5:
            geom = row[hmap.get('geometry', -1)] if 'geometry' in hmap else None
            print(f"roads sample {i}: has_geometry={bool(geom)}")
            continue
        if validate:
            continue
        if Road is None or session is None:
            continue
        try:
            objectid = None
            if 'objectid' in hmap:
                v = row[hmap['objectid']].strip()
                objectid = int(v) if v else None
            name = row[hmap.get('name', -1)].strip() if 'name' in hmap else None
            geom_wkt = row[hmap.get('geometry', -1)] if 'geometry' in hmap else None
            geom = WKTElement(geom_wkt, srid=4326) if geom_wkt else None
            if objectid is not None:
                existing = await session.execute(Road.__table__.select().where(Road.objectid == objectid))
                if existing.first():
                    continue
            session.add(Road(source='rda', objectid=objectid, name=name, geometry=geom, created_at=datetime.utcnow()))
            if total % 100 == 0:
                await session.commit()
        except Exception as exc:
            print(f"road import error: {exc}")
            await session.rollback()
    if fh:
        fh.close()
    if not validate and session is not None:
        await session.commit()
    print(f"roads rows processed: {total}")
    return total


async def import_bus(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "bus_data" / "bus_fares_clean.csv"
    if not path.exists():
        print(f"bus file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        total += 1
        if validate and i <= 5:
            r_no = row[hmap.get('route no', -1)] if 'route no' in hmap else None
            stop = row[hmap.get('stop name', -1)] if 'stop name' in hmap else None
            print(f"bus sample {i}: route={r_no}, stop={stop}")
            continue
        if validate:
            continue
        if BusFare is None or session is None:
            continue
            
        try:
            val_page = row[hmap['page']].strip() if 'page' in hmap else ""
            page = int(val_page) if val_page else None
            
            route_no = row[hmap['route no']].strip() if 'route no' in hmap else None
            from_loc = row[hmap['from']].strip() if 'from' in hmap else None
            to_loc = row[hmap['to']].strip() if 'to' in hmap else None
            via = row[hmap['via']].strip() if 'via' in hmap else None
            
            val_stage = row[hmap['stage no']].strip() if 'stage no' in hmap else ""
            stage_no = int(val_stage) if val_stage else None
            
            val_fare = row[hmap['fare (lkr)']].strip() if 'fare (lkr)' in hmap else ""
            fare = float(val_fare) if val_fare else None
            
            stop_name = row[hmap['stop name']].strip() if 'stop name' in hmap else None
            note = row[hmap['note']].strip() if 'note' in hmap else None
            route_id = row[hmap['route_id']].strip() if 'route_id' in hmap else None
            
            session.add(BusFare(
                page=page,
                route_no=route_no,
                from_loc=from_loc,
                to_loc=to_loc,
                via=via,
                stage_no=stage_no,
                fare_lkr=fare,
                stop_name=stop_name,
                note=note,
                route_id=route_id,
            ))
            if total % 1000 == 0:
                await session.commit()
        except Exception as exc:
            print(f"bus import error at row {i}: {exc}")
            await session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        await session.commit()
    print(f"bus rows processed: {total}")
    return total


async def import_train_stations(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "train_data" / "sri_lanka_stations_Railway.csv"
    if not path.exists():
        print(f"train stations file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        total += 1
        if validate and i <= 5:
            osm_id = row[hmap.get('osm_id', -1)] if 'osm_id' in hmap else None
            name = row[hmap.get('name', -1)] if 'name' in hmap else None
            print(f"train station sample {i}: osm_id={osm_id}, name={name}")
            continue
        if validate:
            continue
        if TrainStation is None or session is None:
            continue
            
        try:
            osm_id = row[hmap['osm_id']].strip() if 'osm_id' in hmap else None
            name = row[hmap['name']].strip() if 'name' in hmap else None
            name_en = row[hmap['name_en']].strip() if 'name_en' in hmap else None
            name_si = row[hmap['name_si']].strip() if 'name_si' in hmap else None
            name_ta = row[hmap['name_ta']].strip() if 'name_ta' in hmap else None
            type_val = row[hmap['type']].strip() if 'type' in hmap else None
            operator = row[hmap['operator']].strip() if 'operator' in hmap else None
            
            val_lat = row[hmap['lat']].strip() if 'lat' in hmap else ""
            lat = float(val_lat) if val_lat else None
            
            val_lon = row[hmap['lon']].strip() if 'lon' in hmap else ""
            lon = float(val_lon) if val_lon else None
            
            session.add(TrainStation(
                osm_id=osm_id,
                name=name,
                name_en=name_en,
                name_si=name_si,
                name_ta=name_ta,
                type=type_val,
                operator=operator,
                lat=lat,
                lon=lon
            ))
            if total % 1000 == 0:
                await session.commit()
        except Exception as exc:
            print(f"train station import error at row {i}: {exc}")
            await session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        await session.commit()
    print(f"train stations rows processed: {total}")
    return total


async def import_train_fares(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "train_data" / "train_price.csv"
    if not path.exists():
        print(f"train fares file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        total += 1
        if validate and i <= 5:
            station = row[hmap.get('station', -1)] if 'station' in hmap else None
            dist = row[hmap.get('distance_km', -1)] if 'distance_km' in hmap else None
            print(f"train fare sample {i}: station={station}, distance={dist}")
            continue
        if validate:
            continue
        if TrainFare is None or session is None:
            continue
            
        try:
            station_name = row[hmap['station']].strip() if 'station' in hmap else None
            val_dist = row[hmap['distance_km']].strip() if 'distance_km' in hmap else ""
            distance_km = float(val_dist) if val_dist else None
            
            val_first = row[hmap['1st_class_rs']].strip() if '1st_class_rs' in hmap else ""
            first_class_rs = float(val_first) if val_first else None
            
            val_second = row[hmap['2nd_class_rs']].strip() if '2nd_class_rs' in hmap else ""
            second_class_rs = float(val_second) if val_second else None
            
            val_third = row[hmap['3rd_class_rs']].strip() if '3rd_class_rs' in hmap else ""
            third_class_rs = float(val_third) if val_third else None
            
            session.add(TrainFare(
                station_name=station_name,
                distance_km=distance_km,
                first_class_rs=first_class_rs,
                second_class_rs=second_class_rs,
                third_class_rs=third_class_rs
            ))
            if total % 1000 == 0:
                await session.commit()
        except Exception as exc:
            print(f"train fare import error at row {i}: {exc}")
            await session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        await session.commit()
    print(f"train fares rows processed: {total}")
    return total


async def main(args):
    total = 0
    if args.roads:
        total += await _with_session(import_roads, validate=args.validate)
    if args.bus:
        total += await _with_session(import_bus, validate=args.validate)
    if args.train_stations:
        total += await _with_session(import_train_stations, validate=args.validate)
    if args.train_fares:
        total += await _with_session(import_train_fares, validate=args.validate)
    print(f"Total processed (or sampled in validate mode): {total}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Import pipeline for Component 2 data')
    parser.add_argument('--roads', action='store_true', help='Import roads data')
    parser.add_argument('--bus', action='store_true', help='Import bus fares data')
    parser.add_argument('--train-stations', action='store_true', help='Import train stations data')
    parser.add_argument('--train-fares', action='store_true', help='Import train fares data')
    parser.add_argument('--validate', action='store_true', help='Dry-run validation')
    args = parser.parse_args()
    asyncio.run(main(args))
