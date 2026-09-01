from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.risk_assessment import RiskAssessmentLevel


class InsightCategory(str, Enum):
    RISK = "Risk"
    ALERT = "Alert"
    ANOMALY = "Anomaly"
    FINANCIAL = "Financial"
    DELAY = "Delay"
    PROGRESS = "Progress"
    DATA_QUALITY = "Data Quality"


class InsightPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RelatedInsightSignal(BaseModel):
    signal_id: int | str
    signal_type: str
    description: str


class SmartInsightResponse(BaseModel):
    insight_id: str
    project_id: int | None
    project_name: str | None
    title: str
    description: str
    category: InsightCategory
    priority: InsightPriority
    relevance_score: float = Field(ge=0, le=100)
    contributing_factors: list[dict[str, Any]]
    recommended_action: str
    created_at: datetime
    related_risk_level: RiskAssessmentLevel | None = None
    related_alerts: list[RelatedInsightSignal] = Field(default_factory=list)
    related_anomaly_signals: list[RelatedInsightSignal] = Field(default_factory=list)


class SmartInsightListResponse(BaseModel):
    items: list[SmartInsightResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class InsightFactorSummary(BaseModel):
    factor: str
    count: int = Field(ge=0)


class InsightActionSummary(BaseModel):
    action: str
    count: int = Field(ge=0)


class SmartInsightSummaryResponse(BaseModel):
    total_insights: int = Field(ge=0)
    critical_insights: int = Field(ge=0)
    high_priority_insights: int = Field(ge=0)
    projects_requiring_attention: int = Field(ge=0)
    top_contributing_factors: list[InsightFactorSummary]
    most_important_recommended_actions: list[InsightActionSummary]


class ProjectInsightsResponse(BaseModel):
    project_id: int
    project_name: str
    items: list[SmartInsightResponse]
    total: int = Field(ge=0)