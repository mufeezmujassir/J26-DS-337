from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DistrictWeatherMonthly(Base):
    __tablename__ = "district_weather_monthly"
    __table_args__ = (
        UniqueConstraint("district_id", "observation_date", name="uq_district_weather_monthly"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False, index=True)
    observation_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    rainfall_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_min_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_max_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_avg_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_station_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    temperature_station_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
