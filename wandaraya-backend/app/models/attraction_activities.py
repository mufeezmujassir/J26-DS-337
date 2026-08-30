from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.database import Base

class AttractionActivity(Base):
    __tablename__ = "attraction_activities"
    __table_args__ = (UniqueConstraint("attraction_id", "activity_id", name="uix_attraction_activity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True)
    suitability_score: Mapped[float] = mapped_column(Float, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=True)
    min_age: Mapped[int] = mapped_column(Integer, nullable=True)
    difficulty_level: Mapped[str] = mapped_column(String(50), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
