from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.dependencies import get_current_user
from app.models.risk_assessment import RiskAssessmentLevel
from app.schemas.alerts import AlertPriority
from app.schemas.reports import (
    ExecutiveReportResponse,
    ReportAlertStatus,
    ReportFilters,
    ReportSummaryResponse,
)
from app.services.report_service import (
    build_executive_report,
    build_report_summary,
)


router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_user)],
)


def _filters(
    project_id: int | None,
    risk_level: RiskAssessmentLevel | None,
    priority: AlertPriority | None,
    alert_status: ReportAlertStatus | None,
) -> ReportFilters:
    return ReportFilters(
        project_id=project_id,
        risk_level=risk_level,
        priority=priority,
        alert_status=alert_status,
    )


@router.get("/summary", response_model=ReportSummaryResponse)
def report_summary(
    project_id: int | None = Query(default=None, ge=1),
    risk_level: RiskAssessmentLevel | None = Query(default=None),
    priority: AlertPriority | None = Query(default=None),
    alert_status: ReportAlertStatus | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return build_report_summary(
        db,
        project_id=project_id,
        risk_level=risk_level,
        priority=priority,
        alert_status=alert_status,
    )


@router.get("/executive", response_model=ExecutiveReportResponse)
def executive_report(
    project_id: int | None = Query(default=None, ge=1),
    risk_level: RiskAssessmentLevel | None = Query(default=None),
    priority: AlertPriority | None = Query(default=None),
    alert_status: ReportAlertStatus | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return build_executive_report(
        db,
        filters=_filters(project_id, risk_level, priority, alert_status),
    )


@router.get("/export", response_model=ExecutiveReportResponse)
def export_report(
    project_id: int | None = Query(default=None, ge=1),
    risk_level: RiskAssessmentLevel | None = Query(default=None),
    priority: AlertPriority | None = Query(default=None),
    alert_status: ReportAlertStatus | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return build_executive_report(
        db,
        filters=_filters(project_id, risk_level, priority, alert_status),
    )