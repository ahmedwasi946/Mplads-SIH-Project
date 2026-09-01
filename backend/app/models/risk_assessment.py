from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
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


class RiskAssessmentLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    overall_risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[RiskAssessmentLevel] = mapped_column(
        SqlEnum(
            RiskAssessmentLevel,
            name="risk_assessment_level",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )
    contributing_factors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )