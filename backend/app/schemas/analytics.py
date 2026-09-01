from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class ProjectMetrics(BaseModel):
    total_projects: int = Field(ge=0)
    planned_projects: int = Field(ge=0)
    ongoing_projects: int = Field(ge=0)
    completed_projects: int = Field(ge=0)
    delayed_projects: int = Field(ge=0)


class FinancialMetrics(BaseModel):
    total_sanctioned_amount: Decimal
    total_utilized_amount: Decimal
    remaining_amount: Decimal
    fund_utilization_percentage: Decimal = Field(ge=0)


class StatusDistributionItem(BaseModel):
    status: ProjectStatus
    project_count: int = Field(ge=0)


class StateProjectDistributionItem(BaseModel):
    state: str
    project_count: int = Field(ge=0)


class StateFinancialDistributionItem(BaseModel):
    state: str
    total_sanctioned_amount: Decimal
    total_utilized_amount: Decimal
    fund_utilization_percentage: Decimal = Field(ge=0)


class RecentProjectItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_name: str
    state: str
    project_status: ProjectStatus
    sanctioned_amount: Decimal
    utilized_amount: Decimal
    created_at: datetime


class DelayedProjectItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_name: str
    state: str
    expected_completion_date: date | None
    project_status: ProjectStatus


class DelayedProjectsSummary(BaseModel):
    total_delayed_projects: int = Field(ge=0)
    projects: list[DelayedProjectItem]


class DashboardAnalyticsResponse(BaseModel):
    project_metrics: ProjectMetrics
    financial_metrics: FinancialMetrics
    status_distribution: list[StatusDistributionItem]
    state_project_distribution: list[StateProjectDistributionItem]
    state_financial_distribution: list[StateFinancialDistributionItem]
    recent_projects: list[RecentProjectItem]
    delayed_projects: DelayedProjectsSummary