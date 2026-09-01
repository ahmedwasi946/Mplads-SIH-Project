from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from app.models.anomaly_detection import AnomalyRiskLevel
from app.models.project import ProjectStatus
from app.models.risk_assessment import RiskAssessmentLevel
from app.schemas.alerts import AlertPriority, RiskAlertResponse


class ReportAlertStatus(str, Enum):
    ALL = "all"
    ACTIVE = "active"


class ReportFilters(BaseModel):
    project_id: int | None = Field(default=None, ge=1)
    risk_level: RiskAssessmentLevel | None = None
    priority: AlertPriority | None = None
    alert_status: ReportAlertStatus | None = None


class ReportSummaryResponse(BaseModel):
    total_projects: int = Field(ge=0)
    total_datasets: int = Field(ge=0)
    total_anomalies: int = Field(ge=0)
    risk_level_distribution: dict[RiskAssessmentLevel, int]
    active_alerts: int = Field(ge=0)
    high_priority_alerts: int = Field(ge=0)
    projects_requiring_attention: int = Field(ge=0)


class ExecutiveOverview(BaseModel):
    total_projects: int = Field(ge=0)
    total_datasets: int = Field(ge=0)
    total_anomalies: int = Field(ge=0)
    active_alerts: int = Field(ge=0)
    projects_requiring_attention: int = Field(ge=0)


class ProjectStatistics(BaseModel):
    total_projects: int = Field(ge=0)
    status_distribution: dict[ProjectStatus, int]
    total_sanctioned_amount: Decimal
    total_utilized_amount: Decimal
    remaining_amount: Decimal
    fund_utilization_percentage: Decimal = Field(ge=0)


class RiskOverview(BaseModel):
    total_assessments: int = Field(ge=0)
    average_risk_score: float = Field(ge=0, le=100)
    risk_level_distribution: dict[RiskAssessmentLevel, int]


class AlertOverview(BaseModel):
    total_alerts: int = Field(ge=0)
    active_alerts: int = Field(ge=0)
    high_priority_alerts: int = Field(ge=0)
    priority_distribution: dict[AlertPriority, int]


class AnomalyOverview(BaseModel):
    total_results: int = Field(ge=0)
    total_anomalies: int = Field(ge=0)
    anomaly_percentage: float = Field(ge=0, le=100)
    risk_level_distribution: dict[AnomalyRiskLevel, int]


class ReportRecommendation(BaseModel):
    alert_id: int
    project_identifier: str
    risk_level: RiskAssessmentLevel
    priority: AlertPriority
    recommendation: str
    created_at: datetime


class ExecutiveReportResponse(BaseModel):
    generated_at: datetime
    filters: ReportFilters
    executive_overview: ExecutiveOverview
    project_statistics: ProjectStatistics
    risk_summary: RiskOverview
    alert_summary: AlertOverview
    anomaly_summary: AnomalyOverview
    high_priority_items: list[RiskAlertResponse]
    recommendations: list[ReportRecommendation]