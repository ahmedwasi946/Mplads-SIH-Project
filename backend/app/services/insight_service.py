from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.anomaly_detection import (
    AnomalyDetectionResult,
    AnomalyRiskLevel,
)
from app.models.dataset import Dataset, DatasetUploadStatus
from app.models.project import Project, ProjectStatus
from app.models.risk_assessment import RiskAssessment, RiskAssessmentLevel
from app.schemas.alerts import AlertPriority
from app.schemas.insights import (
    InsightActionSummary,
    InsightCategory,
    InsightFactorSummary,
    InsightPriority,
    ProjectInsightsResponse,
    RelatedInsightSignal,
    SmartInsightListResponse,
    SmartInsightResponse,
    SmartInsightSummaryResponse,
)
from app.services.alert_service import list_alerts


_RISK_TO_PRIORITY = {
    RiskAssessmentLevel.LOW: InsightPriority.LOW,
    RiskAssessmentLevel.MEDIUM: InsightPriority.MEDIUM,
    RiskAssessmentLevel.HIGH: InsightPriority.HIGH,
    RiskAssessmentLevel.CRITICAL: InsightPriority.CRITICAL,
}

_ANOMALY_TO_PRIORITY = {
    AnomalyRiskLevel.LOW: InsightPriority.LOW,
    AnomalyRiskLevel.MEDIUM: InsightPriority.MEDIUM,
    AnomalyRiskLevel.HIGH: InsightPriority.HIGH,
    AnomalyRiskLevel.CRITICAL: InsightPriority.CRITICAL,
}

_ALERT_TO_PRIORITY = {
    AlertPriority.LOW: InsightPriority.LOW,
    AlertPriority.MEDIUM: InsightPriority.MEDIUM,
    AlertPriority.HIGH: InsightPriority.HIGH,
    AlertPriority.URGENT: InsightPriority.CRITICAL,
}

_PRIORITY_ORDER = {
    InsightPriority.CRITICAL: 0,
    InsightPriority.HIGH: 1,
    InsightPriority.MEDIUM: 2,
    InsightPriority.LOW: 3,
}


def _factor(signal: str, label: str, value: Any) -> dict[str, Any]:
    return {"signal": signal, "label": label, "value": value}


def _factor_dicts(factors: list[Any]) -> list[dict[str, Any]]:
    return [
        factor.model_dump() if hasattr(factor, "model_dump") else factor
        for factor in factors
    ]


def _project_insights(project: Project) -> list[SmartInsightResponse]:
    now = datetime.now(timezone.utc)
    insights: list[SmartInsightResponse] = []
    if project.project_status == ProjectStatus.DELAYED:
        insights.append(
            SmartInsightResponse(
                insight_id=f"project-delay-{project.id}",
                project_id=project.id,
                project_name=project.project_name,
                title="Delayed project requires review",
                description=(
                    f'Project "{project.project_name}" is marked Delayed in the '
                    "project register. This progress signal places it in the "
                    "administrator review queue."
                ),
                category=InsightCategory.DELAY,
                priority=InsightPriority.HIGH,
                relevance_score=90,
                contributing_factors=[
                    _factor("project_status", "Project status", project.project_status.value),
                    _factor(
                        "expected_completion_date",
                        "Expected completion",
                        project.expected_completion_date.isoformat()
                        if project.expected_completion_date
                        else None,
                    ),
                ],
                recommended_action=(
                    "Review the implementation status, expected completion date, "
                    "and current delivery blockers."
                ),
                created_at=project.created_at,
            )
        )

    if project.sanctioned_amount > 0 and project.utilized_amount > project.sanctioned_amount:
        utilization = float(
            (project.utilized_amount / project.sanctioned_amount) * Decimal("100")
        )
        insights.append(
            SmartInsightResponse(
                insight_id=f"project-financial-overrun-{project.id}",
                project_id=project.id,
                project_name=project.project_name,
                title="Utilization exceeds sanctioned amount",
                description=(
                    f'Project "{project.project_name}" has recorded utilization of '
                    f"{utilization:.2f}% against the sanctioned amount. This is a "
                    "financial monitoring signal based on the project register."
                ),
                category=InsightCategory.FINANCIAL,
                priority=InsightPriority.CRITICAL,
                relevance_score=min(utilization, 100),
                contributing_factors=[
                    _factor("sanctioned_amount", "Sanctioned amount", str(project.sanctioned_amount)),
                    _factor("utilized_amount", "Utilized amount", str(project.utilized_amount)),
                    _factor("utilization_percentage", "Utilization", round(utilization, 2)),
                ],
                recommended_action=(
                    "Review the recorded sanctioned and utilized amounts and "
                    "reconcile the project financial register."
                ),
                created_at=project.created_at,
            )
        )
    return insights


def _risk_insight(assessment: RiskAssessment) -> SmartInsightResponse:
    level = assessment.risk_level
    factors = assessment.contributing_factors or [
        _factor("risk_level", "Risk level", level.value),
        _factor("risk_score", "Risk score", assessment.overall_risk_score),
    ]
    if level in {RiskAssessmentLevel.CRITICAL, RiskAssessmentLevel.HIGH}:
        description = (
            f'Source row "{assessment.row_identifier}" has a {level.value} '
            f"risk assessment with score {assessment.overall_risk_score:.1f}/100. "
            f"The stored assessment factors are: "
            f"{', '.join(str(item.get('label') or item.get('signal')) for item in factors)}."
        )
    else:
        description = (
            f'Source row "{assessment.row_identifier}" has a {level.value} '
            f"risk assessment with score {assessment.overall_risk_score:.1f}/100."
        )
    return SmartInsightResponse(
        insight_id=f"risk-assessment-{assessment.id}",
        project_id=None,
        project_name=None,
        title=f"{level.value} risk assessment",
        description=description,
        category=InsightCategory.RISK,
        priority=_RISK_TO_PRIORITY[level],
        relevance_score=assessment.overall_risk_score,
        contributing_factors=factors,
        recommended_action=(
            "Immediate manual review required."
            if level == RiskAssessmentLevel.CRITICAL
            else "Investigate the stored risk factors before deciding next steps."
            if level == RiskAssessmentLevel.HIGH
            else "Monitor the stored risk assessment and review changes."
        ),
        created_at=assessment.assessed_at,
        related_risk_level=level,
        related_alerts=[
            RelatedInsightSignal(
                signal_id=assessment.id,
                signal_type="Phase 8 alert projection",
                description=f"{level.value} alert derived from this risk assessment.",
            )
        ],
    )


def _anomaly_insight(anomaly: AnomalyDetectionResult) -> SmartInsightResponse:
    level = anomaly.risk_level
    factors = anomaly.contributing_features or [
        _factor("anomaly_score", "Anomaly score", anomaly.anomaly_score)
    ]
    return SmartInsightResponse(
        insight_id=f"anomaly-{anomaly.id}",
        project_id=None,
        project_name=None,
        title=f"{level.value} anomaly signal detected",
        description=(
            f'Source row "{anomaly.row_identifier}" is marked as an anomaly with '
            f"score {anomaly.anomaly_score:.3f}. "
            f"{anomaly.explanation or 'Review the stored contributing features.'}"
        ),
        category=InsightCategory.ANOMALY,
        priority=_ANOMALY_TO_PRIORITY[level],
        relevance_score=round(anomaly.anomaly_score * 100, 2),
        contributing_factors=factors,
        recommended_action="Review the contributing anomaly features and source record.",
        created_at=anomaly.detected_at,
        related_anomaly_signals=[
            RelatedInsightSignal(
                signal_id=anomaly.id,
                signal_type="Phase 6 anomaly result",
                description=f"{level.value} anomaly score {anomaly.anomaly_score:.3f}.",
            )
        ],
    )


def _dataset_insight(dataset: Dataset) -> SmartInsightResponse:
    status = dataset.upload_status.value
    return SmartInsightResponse(
        insight_id=f"dataset-quality-{dataset.id}",
        project_id=None,
        project_name=None,
        title="Dataset quality requires attention",
        description=(
            f'Dataset "{dataset.dataset_name}" has status {status} with '
            f"{dataset.total_rows} rows and {dataset.total_columns} columns. "
            "The available dataset metadata is insufficient for normal monitoring."
        ),
        category=InsightCategory.DATA_QUALITY,
        priority=InsightPriority.MEDIUM,
        relevance_score=70,
        contributing_factors=[
            _factor("upload_status", "Upload status", status),
            _factor("total_rows", "Rows", dataset.total_rows),
            _factor("total_columns", "Columns", dataset.total_columns),
        ],
        recommended_action="Review the dataset upload and provide usable monitoring data.",
        created_at=dataset.uploaded_at,
    )


def generate_insights(db: Session) -> list[SmartInsightResponse]:
    insights: list[SmartInsightResponse] = []
    projects = db.scalars(select(Project).order_by(Project.id)).all()
    insights.extend(
        project_insight
        for project in projects
        for project_insight in _project_insights(project)
    )

    assessments = db.scalars(
        select(RiskAssessment).order_by(RiskAssessment.overall_risk_score.desc(), RiskAssessment.id)
    ).all()
    insights.extend(_risk_insight(assessment) for assessment in assessments)

    anomalies = db.scalars(
        select(AnomalyDetectionResult)
        .where(AnomalyDetectionResult.anomaly_detected.is_(True))
        .order_by(AnomalyDetectionResult.anomaly_score.desc(), AnomalyDetectionResult.id)
    ).all()
    insights.extend(_anomaly_insight(anomaly) for anomaly in anomalies)

    datasets = db.scalars(select(Dataset).order_by(Dataset.id)).all()
    insights.extend(
        _dataset_insight(dataset)
        for dataset in datasets
        if dataset.upload_status == DatasetUploadStatus.FAILED
        or dataset.total_rows == 0
        or dataset.total_columns == 0
    )

    alerts, _ = list_alerts(
        db,
        page=1,
        page_size=100,
        risk_level=None,
        priority=None,
    )
    for alert in alerts:
        alert_factors = _factor_dicts(alert.contributing_factors) or [
            _factor("risk_level", "Risk level", alert.risk_level.value),
            _factor("risk_score", "Risk score", alert.risk_score),
        ]
        insights.append(
            SmartInsightResponse(
                insight_id=f"alert-{alert.id}",
                project_id=None,
                project_name=alert.project_name,
                title=f"{alert.priority.value.title()} priority alert",
                description=(
                    f'Alert for source row "{alert.project_identifier}" is '
                    f"{alert.risk_level.value} risk with score {alert.risk_score:.1f}/100. "
                    "This is a decision-support signal from the stored Phase 8 alert."
                ),
                category=InsightCategory.ALERT,
                priority=_ALERT_TO_PRIORITY[alert.priority],
                relevance_score=alert.risk_score,
                contributing_factors=alert_factors,
                recommended_action=alert.recommendation,
                created_at=alert.created_at,
                related_risk_level=alert.risk_level,
                related_alerts=[
                    RelatedInsightSignal(
                        signal_id=alert.id,
                        signal_type="Phase 8 alert",
                        description=alert.recommendation,
                    )
                ],
            )
        )

    return sorted(
        insights,
        key=lambda insight: (
            _PRIORITY_ORDER[insight.priority],
            -insight.relevance_score,
            -insight.created_at.timestamp(),
            insight.insight_id,
        ),
    )


def _filtered_insights(
    db: Session,
    *,
    project_id: int | None = None,
    category: InsightCategory | None = None,
    priority: InsightPriority | None = None,
) -> list[SmartInsightResponse]:
    insights = generate_insights(db)
    if project_id is not None:
        insights = [insight for insight in insights if insight.project_id == project_id]
    if category is not None:
        insights = [insight for insight in insights if insight.category == category]
    if priority is not None:
        insights = [insight for insight in insights if insight.priority == priority]
    return insights


def list_insights(
    db: Session,
    *,
    page: int,
    page_size: int,
    project_id: int | None,
    category: InsightCategory | None,
    priority: InsightPriority | None,
) -> tuple[list[SmartInsightResponse], int]:
    insights = _filtered_insights(
        db,
        project_id=project_id,
        category=category,
        priority=priority,
    )
    start = (page - 1) * page_size
    return insights[start : start + page_size], len(insights)


def build_insight_summary(db: Session) -> SmartInsightSummaryResponse:
    insights = generate_insights(db)
    factor_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    for insight in insights:
        for factor in insight.contributing_factors:
            label = factor.get("label") or factor.get("signal") or factor.get("feature")
            if label:
                factor_counts[str(label)] += 1
        if insight.priority in {InsightPriority.CRITICAL, InsightPriority.HIGH}:
            action_counts[insight.recommended_action] += 1
    attention_projects = {
        insight.project_id
        for insight in insights
        if insight.project_id is not None
        and insight.priority in {InsightPriority.CRITICAL, InsightPriority.HIGH}
    }
    return SmartInsightSummaryResponse(
        total_insights=len(insights),
        critical_insights=sum(
            insight.priority == InsightPriority.CRITICAL for insight in insights
        ),
        high_priority_insights=sum(
            insight.priority == InsightPriority.HIGH for insight in insights
        ),
        projects_requiring_attention=len(attention_projects),
        top_contributing_factors=[
            InsightFactorSummary(factor=factor, count=count)
            for factor, count in factor_counts.most_common(5)
        ],
        most_important_recommended_actions=[
            InsightActionSummary(action=action, count=count)
            for action, count in action_counts.most_common(5)
        ],
    )


def get_project_insights(
    db: Session,
    *,
    project_id: int,
) -> ProjectInsightsResponse | None:
    project = db.get(Project, project_id)
    if project is None:
        return None
    items = _filtered_insights(db, project_id=project_id)
    return ProjectInsightsResponse(
        project_id=project.id,
        project_name=project.project_name,
        items=items,
        total=len(items),
    )