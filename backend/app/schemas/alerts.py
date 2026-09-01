from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.risk_assessment import RiskAssessmentLevel
from app.schemas.risk import RiskFactor


class AlertPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    project_identifier: str
    project_name: str | None
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskAssessmentLevel
    priority: AlertPriority
    contributing_factors: list[RiskFactor]
    recommendation: str
    created_at: datetime


class RiskAlertListResponse(BaseModel):
    items: list[RiskAlertResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class RiskAlertSummaryResponse(BaseModel):
    total_alerts: int = Field(ge=0)
    critical_alerts: int = Field(ge=0)
    high_alerts: int = Field(ge=0)
    medium_alerts: int = Field(ge=0)
    low_alerts: int = Field(ge=0)
    priority_distribution: dict[AlertPriority, int]
    risk_level_distribution: dict[RiskAssessmentLevel, int]