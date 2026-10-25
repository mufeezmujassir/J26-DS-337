"""
WANDARAYA Component 2: Fuel Prices & Vehicle Fuel Efficiency Models
===================================================================
Normalized database models for:
1. Ceylon Petroleum Corporation (CEYPETCO) Official Fuel Price History
2. Manufacturer-Published Vehicle Fuel Efficiency Specifications
"""

from datetime import datetime, date, timezone
from typing import Optional
from sqlalchemy import Float, Integer, String, Boolean, Date, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FuelPrice(Base):
    """
    Official Ceylon Petroleum Corporation (CEYPETCO) Retail Fuel Tariff.
    Source: https://ceypetco.gov.lk/historical-prices/
    """
    __tablename__ = "fuel_prices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fuel_type: Mapped[str] = mapped_column(String(100), index=True)  # e.g., "Petrol 92 Octane", "Auto Diesel"
    price_per_litre_lkr: Mapped[float] = mapped_column(Float, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(
        String(500),
        default="https://ceypetco.gov.lk/historical-prices/"
    )
    source_notice: Mapped[str] = mapped_column(
        String(255),
        default="Ceylon Petroleum Corporation (CEYPETCO) Official Fuel Price Revision"
    )
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "fuel_type": self.fuel_type,
            "price_per_litre_lkr": float(self.price_per_litre_lkr),
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "source_url": self.source_url,
            "source_notice": self.source_notice,
            "last_verified_at": self.last_verified_at.isoformat() if self.last_verified_at else None,
            "is_active": self.is_active,
        }


class VehicleFuelEfficiency(Base):
    """
    Officially Published Manufacturer Specifications and Test-Cycle Consumption Values.
    Maintains laboratory figures (WLTP/JC08/NEDC) strictly distinct from real-world driving results.
    """
    __tablename__ = "vehicle_fuel_efficiency"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    make: Mapped[str] = mapped_column(String(100), index=True)  # e.g., "Suzuki", "Toyota", "Honda"
    model: Mapped[str] = mapped_column(String(150), index=True)  # e.g., "Wagon R", "Prius", "Axio"
    model_year: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g., "2018-2024"
    engine_variant: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)  # e.g., "660cc Mild Hybrid R06A"
    fuel_type: Mapped[str] = mapped_column(String(100), index=True)  # e.g., "Petrol 92 Octane", "Auto Diesel"
    transmission: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "CVT", "Automatic", "Manual"
    hybrid_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "Mild Hybrid", "Full Hybrid", "Conventional ICE"

    # Official published value and its native unit
    published_consumption_value: Mapped[float] = mapped_column(Float, nullable=False)
    consumption_unit: Mapped[str] = mapped_column(String(20), default="km/L")  # "km/L" or "L/100 km"

    # Normalized conversion fields for seamless calculation in either unit
    normalized_km_per_litre: Mapped[float] = mapped_column(Float, nullable=False)
    normalized_l_per_100km: Mapped[float] = mapped_column(Float, nullable=False)

    # Testing and provenance metadata
    test_cycle: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "JC08", "WLTP", "NEDC", "ARAI"
    source_document: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # e.g., "Manufacturer Specification Sheet"
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(100),
        default="VERIFIED_MANUFACTURER_SPECIFICATION"
    )  # "VERIFIED_MANUFACTURER_SPECIFICATION", "USER_ESTIMATE", "CALIBRATED_BENCHMARK"
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "make": self.make,
            "model": self.model,
            "display_name": f"{self.make} {self.model} ({self.engine_variant or self.fuel_type})",
            "model_year": self.model_year,
            "engine_variant": self.engine_variant,
            "fuel_type": self.fuel_type,
            "transmission": self.transmission,
            "hybrid_type": self.hybrid_type,
            "published_consumption_value": float(self.published_consumption_value),
            "consumption_unit": self.consumption_unit,
            "normalized_km_per_litre": round(float(self.normalized_km_per_litre), 2),
            "normalized_l_per_100km": round(float(self.normalized_l_per_100km), 2),
            "test_cycle": self.test_cycle,
            "source_document": self.source_document,
            "source_url": self.source_url,
            "verification_status": self.verification_status,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
        }
