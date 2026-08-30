from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.database import Base

class Attraction(Base):
    __tablename__ = "attractions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True, nullable=True)
    city: Mapped[str] = mapped_column(String(150), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    location: Mapped[dict] = mapped_column(JSON, nullable=True)
    google_place_id: Mapped[str] = mapped_column(String(255), nullable=True, unique=True)
    rating: Mapped[float] = mapped_column(Float, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=True)
    price_level: Mapped[int] = mapped_column(Integer, nullable=True)
    phone_number: Mapped[str] = mapped_column(String(255), nullable=True)
    website_url: Mapped[str] = mapped_column(String(255), nullable=True)
    opening_hours: Mapped[dict] = mapped_column(JSON, nullable=True)
    vibe_tags: Mapped[dict] = mapped_column(JSON, nullable=True)
    experience_tags: Mapped[dict] = mapped_column(JSON, nullable=True)
    best_visit_months: Mapped[dict] = mapped_column(JSON, nullable=True)
    poya_sensitivity: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
