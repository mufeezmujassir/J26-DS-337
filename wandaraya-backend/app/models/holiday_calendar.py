from sqlalchemy import String, Text, Integer, Boolean, Date, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.database import Base

class Holiday(Base):
    __tablename__ = "holiday_calendar"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    is_poya: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_crowd_level: Mapped[str] = mapped_column(String(255), nullable=True)
    affected_regions: Mapped[dict] = mapped_column(JSON, nullable=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
