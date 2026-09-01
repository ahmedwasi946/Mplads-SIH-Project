from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AnomalyRiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class AnomalyDetectionResult(Base):
    __tablename__ = "anomaly_detection_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    anomaly_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[AnomalyRiskLevel] = mapped_column(
        SqlEnum(
            AnomalyRiskLevel,
            name="anomaly_risk_level",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )
    contributing_features: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )