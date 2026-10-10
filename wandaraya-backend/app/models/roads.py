from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Road(Base):
    __tablename__ = "roads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    road_id: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="combined")
    objectid: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    road_number: Mapped[str] = mapped_column(String(50), nullable=True)
    road_class: Mapped[str] = mapped_column(String(50), nullable=True)
    road_type: Mapped[str] = mapped_column(String(50), nullable=True)
    road_condition: Mapped[str] = mapped_column(String(50), nullable=True)
    lanes: Mapped[int] = mapped_column(Integer, nullable=True)
    speed_limit: Mapped[float] = mapped_column(Float, nullable=True)
    bridge_id: Mapped[str] = mapped_column(String(100), nullable=True)
    traffic_volume: Mapped[str] = mapped_column(String(255), nullable=True)
    closure_status: Mapped[str] = mapped_column(String(50), nullable=True)
    start_location: Mapped[str] = mapped_column(String(255), nullable=True)
    end_location: Mapped[str] = mapped_column(String(255), nullable=True)
    total_length_km: Mapped[float] = mapped_column(Float, nullable=True)
    district: Mapped[str] = mapped_column(String(255), nullable=True)
    province: Mapped[str] = mapped_column(String(255), nullable=True)
    geometry = mapped_column(Geometry(geometry_type="MULTILINESTRING", srid=4326), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
