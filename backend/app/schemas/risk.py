from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.risk_assessment import RiskAssessmentLevel


class RiskFactor(BaseModel):
    signal: str
    label: str
    value: float | str
    normalized_value: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=100)


class RiskAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    row_identifier: str
    overall_risk_score: float = Field(ge=0, le=100)
    risk_level: RiskAssessmentLevel
    contributing_factors: list[RiskFactor]
    explanation: str | None
    assessed_at: datetime


class TopRiskFactor(BaseModel):
    factor: str
    occurrence_count: int = Field(ge=0)
    average_contribution: float = Field(ge=0)


class RiskSummaryResponse(BaseModel):
    dataset_id: int
    total_records_assessed: int = Field(ge=0)
    average_risk_score: float = Field(ge=0, le=100)
    risk_level_distribution: dict[RiskAssessmentLevel, int]
    high_risk_count: int = Field(ge=0)
    critical_risk_count: int = Field(ge=0)
    top_contributing_factors: list[TopRiskFactor]
    available_signals: list[str]


class RiskAssessmentListResponse(BaseModel):
    items: list[RiskAssessmentResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)