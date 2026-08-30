from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, Date, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.database import Base

class AttractionReview(Base):
    __tablename__ = "attraction_reviews"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attraction_id: Mapped[int] = mapped_column(ForeignKey("attractions.id"), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=True)
    external_review_id: Mapped[str] = mapped_column(String(255), nullable=True)
    review_text: Mapped[str] = mapped_column(Text, nullable=True)
    rating: Mapped[float] = mapped_column(Float, nullable=True)
    review_date: Mapped[datetime] = mapped_column(Date, nullable=True)
    language: Mapped[str] = mapped_column(String(255), nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str] = mapped_column(String(255), nullable=True)
    review_tags: Mapped[dict] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
