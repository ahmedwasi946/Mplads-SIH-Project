from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class DatasetProcessingStatus(str, Enum):
    PROCESSED = "Processed"
    FAILED = "Failed"


class DatasetProcessingResult(Base):
    __tablename__ = "dataset_processing_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    processed_filename: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    processing_status: Mapped[DatasetProcessingStatus] = mapped_column(
        SqlEnum(
            DatasetProcessingStatus,
            name="dataset_processing_status",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    quality_report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_features: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )