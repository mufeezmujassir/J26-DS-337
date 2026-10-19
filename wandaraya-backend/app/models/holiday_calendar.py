from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Holiday(Base):
    __tablename__ = "holiday_calendar"
    __table_args__ = (UniqueConstraint("event_date", "name", "source_url", name="uq_holiday_calendar_source_record"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_poya: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bank_holiday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_mercantile_holiday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    poya_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    religious_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confirmation_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    expected_crowd_level: Mapped[str | None] = mapped_column(String(255), nullable=True)
    affected_regions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
