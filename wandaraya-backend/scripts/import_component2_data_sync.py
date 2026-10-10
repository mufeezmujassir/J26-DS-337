"""Component 2 import pipeline - step 1: roads.

Validation command:
  python scripts/import_component2_data.py --roads --validate

Import command:
  python scripts/import_component2_data.py --roads
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from geoalchemy2 import WKTElement

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from app.database import AsyncSessionLocal
    from app.models import Road
    from app.models.transport import BusFare, TrainStation, TrainFare
    from app.models.scenic import ScenicPlace
    from app.models.nbro import NBROIncident, NBROInspection, NBROPolygon
except Exception as e:
    print(f"Model Import Error! {e}")
    AsyncSessionLocal = None
    Road = None
    BusFare = None
    TrainStation = None
    TrainFare = None
    ScenicPlace = None
    NBROIncident = None
    NBROInspection = None
    NBROPolygon = None


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


def _with_session(func, *, validate=False):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import os
    db_url = os.environ.get('DATABASE_URL', 'postgresql+psycopg://postgres:root@localhost:5432/wandaraya')
    engine = create_engine(db_url, echo=False)
    SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with SyncSessionLocal() as session:
        return func(session, validate=validate)



def import_roads(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "road_route" / "sri_lanka_all_roads_v4_FINAL (1).csv"
    if not path.exists():
        print(f"roads file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        if i <= 716303:
            continue
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
            road_id = row[hmap['road_id']].strip() if 'road_id' in hmap else None
            name = row[hmap['road_name']].strip() if 'road_name' in hmap else None
            road_number = row[hmap['road_number']].strip() if 'road_number' in hmap else None
            road_class = row[hmap['road_class']].strip() if 'road_class' in hmap else None
            
            val_len = row[hmap['length_km']].strip() if 'length_km' in hmap else ""
            length_km = float(val_len) if val_len else None
            
            road_condition = row[hmap['road_condition']].strip() if 'road_condition' in hmap else None
            surface_type = row[hmap['surface_type']].strip() if 'surface_type' in hmap else None
            
            val_lanes = row[hmap['lanes']].strip() if 'lanes' in hmap else ""
            lanes = int(val_lanes) if val_lanes.isdigit() else None
            
            val_speed = row[hmap['speed_limit']].strip() if 'speed_limit' in hmap else ""
            speed_limit = float(val_speed) if val_speed.replace('.','',1).isdigit() else None
            
            bridge_id = row[hmap['bridge_id']].strip() if 'bridge_id' in hmap else None
            traffic_volume = row[hmap['traffic_volume']].strip() if 'traffic_volume' in hmap else None
            closure_status = row[hmap['closure_status']].strip() if 'closure_status' in hmap else None
            district = row[hmap['district']].strip() if 'district' in hmap else None
            
            geom_wkt = row[hmap['geometry']] if 'geometry' in hmap else None
            geom = WKTElement(geom_wkt, srid=4326) if geom_wkt else None
            
            session.add(Road(
                source='combined_v4',
                road_id=road_id,
                name=name,
                road_number=road_number,
                road_class=road_class,
                road_type=surface_type,
                road_condition=road_condition,
                lanes=lanes,
                speed_limit=speed_limit,
                bridge_id=bridge_id,
                traffic_volume=traffic_volume,
                closure_status=closure_status,
                total_length_km=length_km,
                district=district,
                geometry=geom
            ))
            if i % 5000 == 0:
                print(f"Committing up to row {i}...")
                session.commit()
        except Exception as exc:
            print(f"road import error at row {i}: {exc}")
            session.rollback()
            try:
                error_count += 1
            except NameError:
                error_count = 1
            if error_count > 10:
                print("Too many errors. Aborting.")
                break
    
    if fh:
        fh.close()
    if not validate and session is not None:
        try:
            session.commit()
        except Exception as e:
            print(f"Commit error: {e}")
            session.rollback()
        try:
            session.commit()
        except Exception as e:
            session.rollback()
    print(f"roads rows processed: {total}")
    return total


def import_bus(session, *, validate: bool = False) -> int:
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
            if True:
                session.commit()
        except Exception as exc:
            print(f"bus import error at row {i}: {exc}")
            session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        try:
            session.commit()
        except Exception as e:
            print(f"Commit error: {e}")
            session.rollback()
        session.commit()
    print(f"bus rows processed: {total}")
    return total


def import_train_stations(session, *, validate: bool = False) -> int:
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
            if True:
                session.commit()
        except Exception as exc:
            print(f"train station import error at row {i}: {exc}")
            session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        try:
            session.commit()
        except Exception as e:
            print(f"Commit error: {e}")
            session.rollback()
        session.commit()
    print(f"train stations rows processed: {total}")
    return total


def import_train_fares(session, *, validate: bool = False) -> int:
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
            if True:
                session.commit()
        except Exception as exc:
            print(f"train fare import error at row {i}: {exc}")
            session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        try:
            session.commit()
        except Exception as e:
            print(f"Commit error: {e}")
            session.rollback()
        session.commit()
    print(f"train fares rows processed: {total}")
    return total


def import_scenic_places(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "scenic" / "sri_lanka_combined_scenic_places.csv"
    if not path.exists():
        print(f"scenic places file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        total += 1
        if validate and i <= 5:
            name = row[hmap.get('name', -1)] if 'name' in hmap else None
            cat = row[hmap.get('category', -1)] if 'category' in hmap else None
            print(f"scenic place sample {i}: name={name}, category={cat}")
            continue
        if validate:
            continue
        if ScenicPlace is None or session is None:
            continue
            
        try:
            name = row[hmap['name']].strip() if 'name' in hmap else None
            
            val_lat = row[hmap['latitude']].strip() if 'latitude' in hmap else ""
            latitude = float(val_lat) if val_lat else None
            
            val_lon = row[hmap['longitude']].strip() if 'longitude' in hmap else ""
            longitude = float(val_lon) if val_lon else None
            
            category = row[hmap['category']].strip() if 'category' in hmap else None
            description = row[hmap['description']].strip() if 'description' in hmap else None
            website = row[hmap['website']].strip() if 'website' in hmap else None
            source = row[hmap['source']].strip() if 'source' in hmap else None
            place_type = row[hmap['type']].strip() if 'type' in hmap else None
            address = row[hmap['address']].strip() if 'address' in hmap else None
            district = row[hmap['district']].strip() if 'district' in hmap else None
            
            session.add(ScenicPlace(
                name=name,
                latitude=latitude,
                longitude=longitude,
                category=category,
                description=description,
                website=website,
                source=source,
                type=place_type,
                address=address,
                district=district
            ))
            if True:
                session.commit()
        except Exception as exc:
            print(f"scenic place import error at row {i}: {exc}")
            session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        try:
            session.commit()
        except Exception as e:
            print(f"Commit error: {e}")
            session.rollback()
        session.commit()
    print(f"scenic places rows processed: {total}")
    return total


def import_nbro_incidents(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "NBRO_DATA" / "All_Sri_Lanka_Master.csv"
    if not path.exists():
        print(f"nbro incidents file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        total += 1
        if validate and i <= 5:
            inc_type = row[hmap.get('inc_type', -1)] if 'inc_type' in hmap else None
            district = row[hmap.get('district', -1)] if 'district' in hmap else None
            print(f"nbro incident sample {i}: type={inc_type}, district={district}")
            continue
        if validate:
            continue
        if NBROIncident is None or session is None:
            continue
            
        try:
            val_lat = row[hmap['latitude']].strip() if 'latitude' in hmap else ""
            latitude = float(val_lat) if val_lat and val_lat.replace('.','',1).lstrip('-').isdigit() else None
            
            val_lon = row[hmap['longitude']].strip() if 'longitude' in hmap else ""
            longitude = float(val_lon) if val_lon and val_lon.replace('.','',1).lstrip('-').isdigit() else None
            
            val_r1 = row[hmap['rain_1h']].strip() if 'rain_1h' in hmap else ""
            rain_1h = float(val_r1) if val_r1 and val_r1.replace('.','',1).lstrip('-').isdigit() else None
            
            val_r24 = row[hmap['rain_24h']].strip() if 'rain_24h' in hmap else ""
            rain_24h = float(val_r24) if val_r24 and val_r24.replace('.','',1).lstrip('-').isdigit() else None
            
            val_rcum = row[hmap['rain_cum']].strip() if 'rain_cum' in hmap else ""
            rain_cum = float(val_rcum) if val_rcum and val_rcum.replace('.','',1).lstrip('-').isdigit() else None
            
            session.add(NBROIncident(
                inc_type=row[hmap['inc_type']].strip() if 'inc_type' in hmap else None,
                type_code=row[hmap['type_code']].strip() if 'type_code' in hmap else None,
                request_no=row[hmap['request_no']].strip() if 'request_no' in hmap else None,
                case_id=row[hmap['case_id']].strip() if 'case_id' in hmap else None,
                district=row[hmap['district']].strip() if 'district' in hmap else None,
                ds_name=row[hmap['ds_name']].strip() if 'ds_name' in hmap else None,
                date=row[hmap['date']].strip() if 'date' in hmap else None,
                gnd_name=row[hmap['gnd_name']].strip() if 'gnd_name' in hmap else None,
                gnd_no=row[hmap['gnd_no']].strip() if 'gnd_no' in hmap else None,
                village=row[hmap['village']].strip() if 'village' in hmap else None,
                address=row[hmap['address']].strip() if 'address' in hmap else None,
                pathway=row[hmap['pathway']].strip() if 'pathway' in hmap else None,
                inv_date=row[hmap['inv_date']].strip() if 'inv_date' in hmap else None,
                inc_date=row[hmap['inc_date']].strip() if 'inc_date' in hmap else None,
                inc_time=row[hmap['inc_time']].strip() if 'inc_time' in hmap else None,
                cause=row[hmap['cause']].strip() if 'cause' in hmap else None,
                rain_1h=rain_1h,
                rain_24h=rain_24h,
                rain_cum=rain_cum,
                latitude=latitude,
                longitude=longitude
            ))
            if True:
                session.commit()
        except Exception as exc:
            print(f"nbro incident import error at row {i}: {exc}")
            session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        try:
            session.commit()
        except Exception as e:
            print(f"Commit error: {e}")
            session.rollback()
        session.commit()
    print(f"nbro incidents rows processed: {total}")
    return total

def import_nbro_inspections(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "NBRO_DATA" / "All_Sri_Lanka_Dithawa_HR_Inspections.csv"
    if not path.exists():
        print(f"nbro inspections file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        total += 1
        if validate and i <= 5:
            district = row[hmap.get('district', -1)] if 'district' in hmap else None
            print(f"nbro inspection sample {i}: district={district}")
            continue
        if validate:
            continue
        if NBROInspection is None or session is None:
            continue
            
        try:
            val_lat = row[hmap['latitude']].strip() if 'latitude' in hmap else ""
            if not val_lat and 'lat' in hmap:
                val_lat = row[hmap['lat']].strip()
            latitude = float(val_lat) if val_lat and val_lat.replace('.','',1).lstrip('-').isdigit() else None
            
            val_lon = row[hmap['longitude']].strip() if 'longitude' in hmap else ""
            if not val_lon and 'long' in hmap:
                val_lon = row[hmap['long']].strip()
            longitude = float(val_lon) if val_lon and val_lon.replace('.','',1).lstrip('-').isdigit() else None
            
            val_tr = row[hmap['total_risk']].strip() if 'total_risk' in hmap else ""
            total_risk = float(val_tr) if val_tr and val_tr.replace('.','',1).lstrip('-').isdigit() else None

            session.add(NBROInspection(
                district=row[hmap['district']].strip() if 'district' in hmap else None,
                dsd=row[hmap['dsd']].strip() if 'dsd' in hmap else None,
                gnd_name=row[hmap['gnd_name']].strip() if 'gnd_name' in hmap else None,
                risk_level=row[hmap['risk_level']].strip() if 'risk_level' in hmap else None,
                hr_priorit=row[hmap['hr_priorit']].strip() if 'hr_priorit' in hmap else None,
                ref_no=row[hmap['ref_no']].strip() if 'ref_no' in hmap else None,
                ref_code=row[hmap['ref_code']].strip() if 'ref_code' in hmap else None,
                gnd_num=row[hmap['gnd_num']].strip() if 'gnd_num' in hmap else None,
                const_type=row[hmap['const_type']].strip() if 'const_type' in hmap else None,
                disast_dat=row[hmap['disast_dat']].strip() if 'disast_dat' in hmap else None,
                disast_tim=row[hmap['disast_tim']].strip() if 'disast_tim' in hmap else None,
                insp_date=row[hmap['insp_date']].strip() if 'insp_date' in hmap else None,
                disast_nat=row[hmap['disast_nat']].strip() if 'disast_nat' in hmap else None,
                temp_recom=row[hmap['temp_recom']].strip() if 'temp_recom' in hmap else None,
                damage_lvl=row[hmap['damage_lvl']].strip() if 'damage_lvl' in hmap else None,
                total_risk=total_risk,
                latitude=latitude,
                longitude=longitude
            ))
            if True:
                session.commit()
        except Exception as exc:
            print(f"nbro inspection import error at row {i}: {exc}")
            session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        try:
            session.commit()
        except Exception as e:
            print(f"Commit error: {e}")
            session.rollback()
        session.commit()
    print(f"nbro inspections rows processed: {total}")
    return total

def import_nbro_polygons(session, *, validate: bool = False) -> int:
    path = DATA_DIR / "NBRO_DATA" / "All_Sri_Lanka_Polygons.csv"
    if not path.exists():
        print(f"nbro polygons file not found: {path}")
        return 0

    reader, hmap, fh = _open_csv(path)
    if reader is None:
        return 0

    total = 0
    for i, row in enumerate(reader, start=1):
        total += 1
        if validate and i <= 5:
            district = row[hmap.get('district', -1)] if 'district' in hmap else None
            print(f"nbro polygon sample {i}: district={district}")
            continue
        if validate:
            continue
        if NBROPolygon is None or session is None:
            continue
            
        try:
            val_lat = row[hmap['centroid_latitude']].strip() if 'centroid_latitude' in hmap else ""
            latitude = float(val_lat) if val_lat and val_lat.replace('.','',1).lstrip('-').isdigit() else None
            
            val_lon = row[hmap['centroid_longitude']].strip() if 'centroid_longitude' in hmap else ""
            longitude = float(val_lon) if val_lon and val_lon.replace('.','',1).lstrip('-').isdigit() else None
            
            geom_wkt = row[hmap['wkt_geometry']].strip() if 'wkt_geometry' in hmap else None
            geom = WKTElement(geom_wkt, srid=4326) if geom_wkt else None
            
            session.add(NBROPolygon(
                name=row[hmap['name']].strip() if 'name' in hmap else None,
                descript=row[hmap['descript']].strip() if 'descript' in hmap else None,
                source_kmz=row[hmap['source_kmz']].strip() if 'source_kmz' in hmap else None,
                layer_name=row[hmap['layer_name']].strip() if 'layer_name' in hmap else None,
                district=row[hmap['district']].strip() if 'district' in hmap else None,
                centroid_latitude=latitude,
                centroid_longitude=longitude,
                wkt_geometry=geom
            ))
            if True:
                session.commit()
        except Exception as exc:
            print(f"nbro polygon import error at row {i}: {exc}")
            session.rollback()
            
    if fh:
        fh.close()
    if not validate and session is not None:
        try:
            session.commit()
        except Exception as e:
            print(f"Commit error: {e}")
            session.rollback()
        session.commit()
    print(f"nbro polygons rows processed: {total}")
    return total

def main(args):
    total = 0
    if args.roads:
        total += _with_session(import_roads, validate=args.validate)
    if args.bus:
        total += _with_session(import_bus, validate=args.validate)
    if args.train_stations:
        total += _with_session(import_train_stations, validate=args.validate)
    if args.train_fares:
        total += _with_session(import_train_fares, validate=args.validate)
    if args.scenic:
        total += _with_session(import_scenic_places, validate=args.validate)
    if args.nbro:
        total += _with_session(import_nbro_incidents, validate=args.validate)
        total += _with_session(import_nbro_inspections, validate=args.validate)
        total += _with_session(import_nbro_polygons, validate=args.validate)
    print(f"Total processed (or sampled in validate mode): {total}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Import pipeline for Component 2 data')
    parser.add_argument('--roads', action='store_true', help='Import roads data')
    parser.add_argument('--bus', action='store_true', help='Import bus fares data')
    parser.add_argument('--train-stations', action='store_true', help='Import train stations data')
    parser.add_argument('--train-fares', action='store_true', help='Import train fares data')
    parser.add_argument('--scenic', action='store_true', help='Import scenic places data')
    parser.add_argument('--nbro', action='store_true', help='Import nbro datasets data')
    parser.add_argument('--validate', action='store_true', help='Dry-run validation')
    args = parser.parse_args()
    main(args)
