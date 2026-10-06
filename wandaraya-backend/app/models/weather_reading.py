from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.database import Base
from sqlalchemy import Column, BigInteger, ForeignKey, Date, Time, func

class WeatherReading(Base):

    __tablename__ = "weather_readings"

    id = Column(
        BigInteger,
        primary_key=True,
    )

    station_id = Column(
        String(50),
        nullable=False,
    )

    station_name = Column(
        String(150),
        nullable=False,
    )

    district_id = Column(
        Integer,
        ForeignKey(
            "districts.id"
        ),
        nullable=True,
    )

    latitude = Column(
        Float,
        nullable=True,
    )

    longitude = Column(
        Float,
        nullable=True,
    )

    observation_date = Column(
        Date,
        nullable=False,
    )

    rainfall_mm = Column(
        Float,
        nullable=True,
    )

    temperature_min_c = Column(
        Float,
        nullable=True,
    )

    temperature_max_c = Column(
        Float,
        nullable=True,
    )

    humidity_percent = Column(
        Float,
        nullable=True,
    )

    source = Column(
        String(100),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )