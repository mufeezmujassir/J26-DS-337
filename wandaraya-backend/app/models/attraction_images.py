from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Text,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AttractionImage(Base):
    """
    Stores image metadata associated with a tourism attraction.

    Important:

    - A single MinIO object can only be registered once.
    """

    __tablename__ = "attraction_images"

    __table_args__ = (
        # Prevent the same MinIO object from being registered twice
        UniqueConstraint(
            "bucket_name",
            "storage_key",
            name="uix_attraction_image_storage",
        ),

        Index(
            "ix_attraction_images_attraction_active",
            "attraction_id",
            "is_active",
        ),

        Index(
            "ix_attraction_images_attraction_primary",
            "attraction_id",
            "is_primary",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

  
    attraction_id: Mapped[int] = mapped_column(
        ForeignKey(
            "attractions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "data_sources.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    original_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

  
    external_image_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

   
    bucket_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

  
    storage_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

   
    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

   
    file_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    attribution: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

   
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

   
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    
    retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Last time this image/source was synchronized.
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )