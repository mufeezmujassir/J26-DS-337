from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.database import Base

class AttractionCategory(Base):
    __tablename__ = "attraction_categories"
    __table_args__ = (UniqueConstraint("attraction_id", "category_id", name="uix_attraction_category"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
