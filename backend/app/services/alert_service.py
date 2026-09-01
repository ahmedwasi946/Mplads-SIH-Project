from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.risk_assessment import RiskAssessment, RiskAssessmentLevel
from app.schemas.alerts import (
    AlertPriority,
    RiskAlertResponse,
    RiskAlertSummaryResponse,
)


_ALERT_RULES: dict[RiskAssessmentLevel, tuple[AlertPriority, str]] = {
    RiskAssessmentLevel.CRITICAL: (
        AlertPriority.URGENT,
        "Immediate manual review required.",
    ),
    RiskAssessmentLevel.HIGH: (
        AlertPriority.HIGH,
        "Investigate contributing anomaly, financial, delay, or progress signals.",
    ),
    RiskAssessmentLevel.MEDIUM: (
        AlertPriority.MEDIUM,
        "Monitor the project and review changes.",
    ),
    RiskAssessmentLevel.LOW: (
        AlertPriority.LOW,
        "Continue regular monitoring.",
    ),
}

_RISK_LEVEL_FOR_PRIORITY = {
    priority: risk_level
    for risk_level, (priority, _) in _ALERT_RULES.items()
}


def _to_alert(assessment: RiskAssessment) -> RiskAlertResponse:
    priority, recommendation = _ALERT_RULES[assessment.risk_level]
    return RiskAlertResponse(
        id=assessment.id,
        dataset_id=assessment.dataset_id,
        # Phase 7 stores the stable source-row identifier, which is the only
        # project identifier available when a dataset is not linked to Projects.
        project_identifier=assessment.row_identifier,
        project_name=None,
        risk_score=assessment.overall_risk_score,
        risk_level=assessment.risk_level,
        priority=priority,
        contributing_factors=assessment.contributing_factors,
        recommendation=recommendation,
        created_at=assessment.assessed_at,
    )


def _priority_order():
    return case(
        (RiskAssessment.risk_level == RiskAssessmentLevel.CRITICAL, 0),
        (RiskAssessment.risk_level == RiskAssessmentLevel.HIGH, 1),
        (RiskAssessment.risk_level == RiskAssessmentLevel.MEDIUM, 2),
        else_=3,
    )


def list_alerts(
    db: Session,
    *,
    page: int,
    page_size: int,
    risk_level: RiskAssessmentLevel | None,
    priority: AlertPriority | None,
) -> tuple[list[RiskAlertResponse], int]:
    filters = []
    if risk_level is not None:
        filters.append(RiskAssessment.risk_level == risk_level)
    if priority is not None:
        filters.append(
            RiskAssessment.risk_level == _RISK_LEVEL_FOR_PRIORITY[priority]
        )

    total = db.scalar(
        select(func.count(RiskAssessment.id)).where(*filters)
    ) or 0
    assessments = db.scalars(
        select(RiskAssessment)
        .where(*filters)
        .order_by(
            _priority_order(),
            RiskAssessment.overall_risk_score.desc(),
            RiskAssessment.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_to_alert(assessment) for assessment in assessments], int(total)


def get_alert(alert_id: int, db: Session) -> RiskAlertResponse | None:
    assessment = db.get(RiskAssessment, alert_id)
    return _to_alert(assessment) if assessment is not None else None


def build_alert_summary(db: Session) -> RiskAlertSummaryResponse:
    counts = {
        risk_level: 0
        for risk_level in RiskAssessmentLevel
    }
    grouped_counts = db.execute(
        select(
            RiskAssessment.risk_level,
            func.count(RiskAssessment.id),
        ).group_by(RiskAssessment.risk_level)
    ).all()
    for risk_level, count in grouped_counts:
        counts[risk_level] = int(count)

    priority_distribution = {
        priority: counts[_RISK_LEVEL_FOR_PRIORITY[priority]]
        for priority in AlertPriority
    }
    return RiskAlertSummaryResponse(
        total_alerts=sum(counts.values()),
        critical_alerts=counts[RiskAssessmentLevel.CRITICAL],
        high_alerts=counts[RiskAssessmentLevel.HIGH],
        medium_alerts=counts[RiskAssessmentLevel.MEDIUM],
        low_alerts=counts[RiskAssessmentLevel.LOW],
        priority_distribution=priority_distribution,
        risk_level_distribution=counts,
    )