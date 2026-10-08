from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from app.database import Base


class WeatherReading(Base):

    __tablename__ = "weather_readings"

    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "observation_date",
            name="uq_weather_reading_station_date",
        ),
    )

    id = Column(
        BigInteger,
        primary_key=True,
    )

    station_id = Column(
        String(50),
        ForeignKey(
            "weather_stations.station_id"
        ),
        nullable=False,
        index=True,
    )

    station_name = Column(
        String(150),
        nullable=False,
    )

    district_id = Column(
        Integer,
        ForeignKey("districts.id"),
        nullable=True,
        index=True,
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
        index=True,
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