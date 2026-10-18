from datetime import datetime, timezone
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class BusFare(Base):
    __tablename__ = "bus_fares"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    page: Mapped[int] = mapped_column(Integer, nullable=True)
    route_no: Mapped[str] = mapped_column(String(50), nullable=True)
    from_loc: Mapped[str] = mapped_column(String(255), nullable=True)
    to_loc: Mapped[str] = mapped_column(String(255), nullable=True)
    via: Mapped[str] = mapped_column(String(255), nullable=True)
    stage_no: Mapped[int] = mapped_column(Integer, nullable=True)
    fare_lkr: Mapped[float] = mapped_column(Float, nullable=True)
    stop_name: Mapped[str] = mapped_column(String(255), nullable=True)
    note: Mapped[str] = mapped_column(String(255), nullable=True)
    route_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

class TrainStation(Base):
    __tablename__ = "train_stations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    osm_id: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    name_en: Mapped[str] = mapped_column(String(255), nullable=True)
    name_si: Mapped[str] = mapped_column(String(255), nullable=True)
    name_ta: Mapped[str] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(100), nullable=True)
    operator: Mapped[str] = mapped_column(String(255), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=True)
    lon: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

class TrainFare(Base):
    __tablename__ = "train_fares"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_name: Mapped[str] = mapped_column(String(255), nullable=True)
    distance_km: Mapped[float] = mapped_column(Float, nullable=True)
    first_class_rs: Mapped[float] = mapped_column(Float, nullable=True)
    second_class_rs: Mapped[float] = mapped_column(Float, nullable=True)
    third_class_rs: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
