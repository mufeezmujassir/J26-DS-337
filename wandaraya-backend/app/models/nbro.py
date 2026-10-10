from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NBROIncident(Base):
    __tablename__ = "nbro_incidents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inc_type: Mapped[str] = mapped_column(String(100), nullable=True)
    type_code: Mapped[str] = mapped_column(String(50), nullable=True)
    request_no: Mapped[str] = mapped_column(String(50), nullable=True)
    case_id: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    district: Mapped[str] = mapped_column(String(100), nullable=True)
    ds_name: Mapped[str] = mapped_column(String(100), nullable=True)
    date: Mapped[str] = mapped_column(String(50), nullable=True)
    gnd_name: Mapped[str] = mapped_column(String(150), nullable=True)
    gnd_no: Mapped[str] = mapped_column(String(50), nullable=True)
    village: Mapped[str] = mapped_column(String(150), nullable=True)
    address: Mapped[str] = mapped_column(Text, nullable=True)
    pathway: Mapped[str] = mapped_column(String(255), nullable=True)
    inv_date: Mapped[str] = mapped_column(String(50), nullable=True)
    inc_date: Mapped[str] = mapped_column(String(50), nullable=True)
    inc_time: Mapped[str] = mapped_column(String(50), nullable=True)
    cause: Mapped[str] = mapped_column(Text, nullable=True)
    rain_1h: Mapped[float] = mapped_column(Float, nullable=True)
    rain_24h: Mapped[float] = mapped_column(Float, nullable=True)
    rain_cum: Mapped[float] = mapped_column(Float, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


class NBROInspection(Base):
    __tablename__ = "nbro_inspections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    district: Mapped[str] = mapped_column(String(100), nullable=True)
    dsd: Mapped[str] = mapped_column(String(100), nullable=True)
    gnd_name: Mapped[str] = mapped_column(String(150), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=True)
    hr_priorit: Mapped[str] = mapped_column(String(50), nullable=True)
    ref_no: Mapped[str] = mapped_column(String(50), nullable=True)
    ref_code: Mapped[str] = mapped_column(String(50), nullable=True)
    gnd_num: Mapped[str] = mapped_column(String(50), nullable=True)
    const_type: Mapped[str] = mapped_column(String(100), nullable=True)
    disast_dat: Mapped[str] = mapped_column(String(50), nullable=True)
    disast_tim: Mapped[str] = mapped_column(String(50), nullable=True)
    insp_date: Mapped[str] = mapped_column(String(50), nullable=True)
    disast_nat: Mapped[str] = mapped_column(String(150), nullable=True)
    temp_recom: Mapped[str] = mapped_column(Text, nullable=True)
    damage_lvl: Mapped[str] = mapped_column(String(50), nullable=True)
    total_risk: Mapped[float] = mapped_column(Float, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


class NBROPolygon(Base):
    __tablename__ = "nbro_polygons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    descript: Mapped[str] = mapped_column(Text, nullable=True)
    source_kmz: Mapped[str] = mapped_column(String(255), nullable=True)
    layer_name: Mapped[str] = mapped_column(String(255), nullable=True)
    district: Mapped[str] = mapped_column(String(100), nullable=True)
    centroid_longitude: Mapped[float] = mapped_column(Float, nullable=True)
    centroid_latitude: Mapped[float] = mapped_column(Float, nullable=True)
    wkt_geometry = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
