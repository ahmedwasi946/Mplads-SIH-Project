from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.anomaly_detection import (
    AnomalyDetectionResult,
    AnomalyRiskLevel,
)
from app.models.dataset import Dataset
from app.models.project import Project, ProjectStatus
from app.models.risk_assessment import RiskAssessment, RiskAssessmentLevel
from app.schemas.alerts import AlertPriority
from app.schemas.reports import (
    AlertOverview,
    AnomalyOverview,
    ExecutiveOverview,
    ExecutiveReportResponse,
    ProjectStatistics,
    ReportAlertStatus,
    ReportFilters,
    ReportRecommendation,
    ReportSummaryResponse,
    RiskOverview,
)
from app.services.alert_service import (
    build_alert_summary,
    list_alerts,
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


def _risk_filters(
    *,
    risk_level: RiskAssessmentLevel | None,
    priority: AlertPriority | None,
):
    filters = []
    if risk_level is not None:
        filters.append(RiskAssessment.risk_level == risk_level)
    if priority is not None:
        priority_to_level = {
            AlertPriority.URGENT: RiskAssessmentLevel.CRITICAL,
            AlertPriority.HIGH: RiskAssessmentLevel.HIGH,
            AlertPriority.MEDIUM: RiskAssessmentLevel.MEDIUM,
            AlertPriority.LOW: RiskAssessmentLevel.LOW,
        }
        filters.append(RiskAssessment.risk_level == priority_to_level[priority])
    return filters


def _project_filters(project_id: int | None):
    return [Project.id == project_id] if project_id is not None else []


def _risk_distribution(
    db: Session,
    *,
    risk_level: RiskAssessmentLevel | None,
    priority: AlertPriority | None,
) -> dict[RiskAssessmentLevel, int]:
    distribution = {level: 0 for level in RiskAssessmentLevel}
    rows = db.execute(
        select(
            RiskAssessment.risk_level,
            func.count(RiskAssessment.id),
        )
        .where(*_risk_filters(risk_level=risk_level, priority=priority))
        .group_by(RiskAssessment.risk_level)
    ).all()
    for level, count in rows:
        distribution[level] = int(count)
    return distribution


def _anomaly_overview(
    db: Session,
    *,
    risk_level: RiskAssessmentLevel | None,
) -> AnomalyOverview:
    filters = []
    if risk_level is not None:
        filters.append(AnomalyDetectionResult.risk_level == risk_level)
    rows = db.execute(
        select(
            AnomalyDetectionResult.risk_level,
            func.count(AnomalyDetectionResult.id),
            func.sum(
                case(
                    (AnomalyDetectionResult.anomaly_detected.is_(True), 1),
                    else_=0,
                )
            ),
        )
        .where(*filters)
        .group_by(AnomalyDetectionResult.risk_level)
    ).all()
    distribution = {level: 0 for level in AnomalyRiskLevel}
    total_results = 0
    total_anomalies = 0
    for level, count, anomaly_count in rows:
        distribution[level] = int(count)
        total_results += int(count)
        total_anomalies += int(anomaly_count or 0)
    return AnomalyOverview(
        total_results=total_results,
        total_anomalies=total_anomalies,
        anomaly_percentage=round(
            (total_anomalies / total_results) * 100,
            2,
        )
        if total_results
        else 0.0,
        risk_level_distribution=distribution,
    )


def _project_statistics(db: Session, project_id: int | None) -> ProjectStatistics:
    filters = _project_filters(project_id)
    projects = list(
        db.scalars(select(Project).where(*filters).order_by(Project.id)).all()
    )
    status_distribution = Counter(project.project_status for project in projects)
    total_sanctioned = _money(
        sum((project.sanctioned_amount for project in projects), ZERO)
    )
    total_utilized = _money(
        sum((project.utilized_amount for project in projects), ZERO)
    )
    return ProjectStatistics(
        total_projects=len(projects),
        status_distribution={
            status: int(status_distribution.get(status, 0))
            for status in ProjectStatus
        },
        total_sanctioned_amount=total_sanctioned,
        total_utilized_amount=total_utilized,
        remaining_amount=_money(total_sanctioned - total_utilized),
        fund_utilization_percentage=_percentage(total_utilized, total_sanctioned),
    )


def _total_datasets(db: Session) -> int:
    return int(db.scalar(select(func.count(Dataset.id))) or 0)


def _projects_requiring_attention(
    db: Session,
    *,
    project_id: int | None,
    risk_level: RiskAssessmentLevel | None,
    priority: AlertPriority | None,
) -> int:
    delayed_projects = int(
        db.scalar(
            select(func.count(Project.id)).where(
                Project.project_status == ProjectStatus.DELAYED,
                *_project_filters(project_id),
            )
        )
        or 0
    )
    risk_filters = _risk_filters(risk_level=risk_level, priority=priority)
    high_risk_records = int(
        db.scalar(
            select(func.count(func.distinct(RiskAssessment.row_identifier))).where(
                *risk_filters,
                RiskAssessment.risk_level.in_(
                    [RiskAssessmentLevel.HIGH, RiskAssessmentLevel.CRITICAL]
                ),
            )
        )
        or 0
    )
    return delayed_projects + high_risk_records


def build_report_summary(
    db: Session,
    *,
    project_id: int | None,
    risk_level: RiskAssessmentLevel | None,
    priority: AlertPriority | None,
    alert_status: ReportAlertStatus | None,
) -> ReportSummaryResponse:
    project_statistics = _project_statistics(db, project_id)
    anomaly_summary = _anomaly_overview(db, risk_level=risk_level)
    risk_distribution = _risk_distribution(
        db,
        risk_level=risk_level,
        priority=priority,
    )
    alert_summary = build_alert_summary(db)
    alert_items, _ = list_alerts(
        db,
        page=1,
        page_size=100,
        risk_level=risk_level,
        priority=priority,
    )
    if alert_status in {ReportAlertStatus.ALL, ReportAlertStatus.ACTIVE, None}:
        filtered_alerts = alert_items
    else:
        filtered_alerts = []
    high_priority_alerts = sum(
        item.priority in {AlertPriority.URGENT, AlertPriority.HIGH}
        for item in filtered_alerts
    )
    return ReportSummaryResponse(
        total_projects=project_statistics.total_projects,
        total_datasets=_total_datasets(db),
        total_anomalies=anomaly_summary.total_anomalies,
        risk_level_distribution=risk_distribution,
        active_alerts=len(filtered_alerts),
        high_priority_alerts=high_priority_alerts,
        projects_requiring_attention=_projects_requiring_attention(
            db,
            project_id=project_id,
            risk_level=risk_level,
            priority=priority,
        ),
    )


def build_executive_report(
    db: Session,
    *,
    filters: ReportFilters,
) -> ExecutiveReportResponse:
    project_statistics = _project_statistics(db, filters.project_id)
    anomaly_summary = _anomaly_overview(db, risk_level=filters.risk_level)
    risk_distribution = _risk_distribution(
        db,
        risk_level=filters.risk_level,
        priority=filters.priority,
    )
    risk_stats = db.execute(
        select(
            func.count(RiskAssessment.id),
            func.avg(RiskAssessment.overall_risk_score),
        ).where(
            *_risk_filters(
                risk_level=filters.risk_level,
                priority=filters.priority,
            )
        )
    ).one()
    total_assessments = int(risk_stats[0] or 0)
    average_risk_score = float(risk_stats[1] or 0)
    risk_overview = RiskOverview(
        total_assessments=total_assessments,
        average_risk_score=round(average_risk_score, 2),
        risk_level_distribution=risk_distribution,
    )

    alert_items, _ = list_alerts(
        db,
        page=1,
        page_size=100,
        risk_level=filters.risk_level,
        priority=filters.priority,
    )
    active_alerts = (
        alert_items
        if filters.alert_status in {None, ReportAlertStatus.ALL, ReportAlertStatus.ACTIVE}
        else []
    )
    priority_distribution = {
        priority: 0
        for priority in AlertPriority
    }
    for item in active_alerts:
        priority_distribution[item.priority] += 1
    alert_overview = AlertOverview(
        total_alerts=len(active_alerts),
        active_alerts=len(active_alerts),
        high_priority_alerts=sum(
            item.priority in {AlertPriority.URGENT, AlertPriority.HIGH}
            for item in active_alerts
        ),
        priority_distribution=priority_distribution,
    )
    high_priority_items = [
        item
        for item in active_alerts
        if item.priority in {AlertPriority.URGENT, AlertPriority.HIGH}
    ][:10]
    recommendations = [
        ReportRecommendation(
            alert_id=item.id,
            project_identifier=item.project_identifier,
            risk_level=item.risk_level,
            priority=item.priority,
            recommendation=item.recommendation,
            created_at=item.created_at,
        )
        for item in active_alerts[:20]
    ]
    projects_requiring_attention = _projects_requiring_attention(
        db,
        project_id=filters.project_id,
        risk_level=filters.risk_level,
        priority=filters.priority,
    )
    total_datasets = _total_datasets(db)
    return ExecutiveReportResponse(
        generated_at=datetime.now(timezone.utc),
        filters=filters,
        executive_overview=ExecutiveOverview(
            total_projects=project_statistics.total_projects,
            total_datasets=total_datasets,
            total_anomalies=anomaly_summary.total_anomalies,
            active_alerts=len(active_alerts),
            projects_requiring_attention=projects_requiring_attention,
        ),
        project_statistics=project_statistics,
        risk_summary=risk_overview,
        alert_summary=alert_overview,
        anomaly_summary=anomaly_summary,
        high_priority_items=high_priority_items,
        recommendations=recommendations,
    )