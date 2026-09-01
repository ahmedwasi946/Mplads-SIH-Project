from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.dependencies import get_current_user
from app.models.risk_assessment import RiskAssessmentLevel
from app.schemas.alerts import (
    AlertPriority,
    RiskAlertListResponse,
    RiskAlertResponse,
    RiskAlertSummaryResponse,
)
from app.services.alert_service import (
    build_alert_summary,
    get_alert,
    list_alerts,
)


router = APIRouter(
    prefix="/alerts",
    tags=["risk-alerts"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=RiskAlertListResponse)
def get_alerts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    risk_level: RiskAssessmentLevel | None = Query(default=None),
    priority: AlertPriority | None = Query(default=None),
    db: Session = Depends(get_db),
):
    items, total = list_alerts(
        db,
        page=page,
        page_size=page_size,
        risk_level=risk_level,
        priority=priority,
    )
    return RiskAlertListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get("/summary", response_model=RiskAlertSummaryResponse)
def get_alert_summary(db: Session = Depends(get_db)):
    return build_alert_summary(db)


@router.get("/{alert_id}", response_model=RiskAlertResponse)
def get_alert_detail(alert_id: int, db: Session = Depends(get_db)):
    alert = get_alert(alert_id, db)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk alert not found.",
        )
    return alert