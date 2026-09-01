from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectStatus
from app.schemas.analytics import (
    DashboardAnalyticsResponse,
    DelayedProjectsSummary,
    FinancialMetrics,
    ProjectMetrics,
    RecentProjectItem,
    StateFinancialDistributionItem,
    StateProjectDistributionItem,
    StatusDistributionItem,
)

ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")


def _money(value: Decimal | int | None) -> Decimal:
    if value is None:
        return ZERO.quantize(TWO_PLACES)
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _percentage(utilized: Decimal, sanctioned: Decimal) -> Decimal:
    if sanctioned == ZERO:
        return ZERO.quantize(TWO_PLACES)
    return ((utilized / sanctioned) * Decimal("100")).quantize(
        TWO_PLACES,
        rounding=ROUND_HALF_UP,
    )


def get_dashboard_analytics(db: Session) -> DashboardAnalyticsResponse:
    status_rows = db.execute(
        select(Project.project_status, func.count(Project.id))
        .group_by(Project.project_status)
    ).all()
    status_counts = {status: count for status, count in status_rows}

    total_projects = sum(status_counts.values())
    project_metrics = ProjectMetrics(
        total_projects=total_projects,
        planned_projects=status_counts.get(ProjectStatus.PLANNED, 0),
        ongoing_projects=status_counts.get(ProjectStatus.ONGOING, 0),
        completed_projects=status_counts.get(ProjectStatus.COMPLETED, 0),
        delayed_projects=status_counts.get(ProjectStatus.DELAYED, 0),
    )

    financial_row = db.execute(
        select(
            func.coalesce(func.sum(Project.sanctioned_amount), ZERO),
            func.coalesce(func.sum(Project.utilized_amount), ZERO),
        )
    ).one()
    total_sanctioned = _money(financial_row[0])
    total_utilized = _money(financial_row[1])
    financial_metrics = FinancialMetrics(
        total_sanctioned_amount=total_sanctioned,
        total_utilized_amount=total_utilized,
        remaining_amount=_money(total_sanctioned - total_utilized),
        fund_utilization_percentage=_percentage(
            total_utilized,
            total_sanctioned,
        ),
    )

    state_rows = db.execute(
        select(
            Project.state,
            func.count(Project.id),
            func.coalesce(func.sum(Project.sanctioned_amount), ZERO),
            func.coalesce(func.sum(Project.utilized_amount), ZERO),
        )
        .group_by(Project.state)
        .order_by(Project.state)
    ).all()

    status_distribution = [
        StatusDistributionItem(
            status=status,
            project_count=status_counts.get(status, 0),
        )
        for status in ProjectStatus
    ]
    state_project_distribution = [
        StateProjectDistributionItem(state=state, project_count=count)
        for state, count, _, _ in state_rows
    ]
    state_financial_distribution = [
        StateFinancialDistributionItem(
            state=state,
            total_sanctioned_amount=_money(sanctioned),
            total_utilized_amount=_money(utilized),
            fund_utilization_percentage=_percentage(
                _money(utilized),
                _money(sanctioned),
            ),
        )
        for state, _, sanctioned, utilized in state_rows
    ]

    recent_projects = list(
        db.scalars(
            select(Project)
            .order_by(desc(Project.created_at), desc(Project.id))
            .limit(5)
        ).all()
    )
    recent_project_items = [
        RecentProjectItem.model_validate(project)
        for project in recent_projects
    ]

    delayed_projects = list(
        db.scalars(
            select(Project)
            .where(Project.project_status == ProjectStatus.DELAYED)
            .order_by(desc(Project.created_at), desc(Project.id))
        ).all()
    )
    delayed_summary = DelayedProjectsSummary(
        total_delayed_projects=len(delayed_projects),
        projects=[
            {
                "id": project.id,
                "project_name": project.project_name,
                "state": project.state,
                "expected_completion_date": project.expected_completion_date,
                "project_status": project.project_status,
            }
            for project in delayed_projects
        ],
    )

    return DashboardAnalyticsResponse(
        project_metrics=project_metrics,
        financial_metrics=financial_metrics,
        status_distribution=status_distribution,
        state_project_distribution=state_project_distribution,
        state_financial_distribution=state_financial_distribution,
        recent_projects=recent_project_items,
        delayed_projects=delayed_summary,
    )