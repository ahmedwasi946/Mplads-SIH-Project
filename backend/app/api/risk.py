from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.db.database import get_db
from app.models.dataset import Dataset
from app.models.risk_assessment import RiskAssessmentLevel
from app.models.user import User, UserRole
from app.schemas.risk import (
    RiskAssessmentListResponse,
    RiskAssessmentResponse,
    RiskSummaryResponse,
)
from app.services.risk_scoring_service import (
    build_risk_summary,
    calculate_and_store_risk,
    list_risk_assessments,
)


router = APIRouter(
    prefix="/datasets",
    tags=["risk-scoring"],
    dependencies=[Depends(get_current_user)],
)


def _get_dataset_or_404(dataset_id: int, db: Session) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    return dataset


@router.post(
    "/{dataset_id}/calculate-risk",
    response_model=RiskSummaryResponse,
)
def calculate_dataset_risk(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.GOVERNMENT_OFFICER,
            UserRole.ANALYST,
        )
    ),
):
    dataset = _get_dataset_or_404(dataset_id, db)
    try:
        return calculate_and_store_risk(dataset, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Risk assessment could not be completed.",
        ) from exc


@router.get(
    "/{dataset_id}/risk-assessments",
    response_model=RiskAssessmentListResponse,
)
def get_risk_assessments(
    dataset_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    risk_level: RiskAssessmentLevel | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _get_dataset_or_404(dataset_id, db)
    results, total = list_risk_assessments(
        dataset_id,
        db,
        page=page,
        page_size=page_size,
        risk_level=risk_level,
    )
    return RiskAssessmentListResponse(
        items=results,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get(
    "/{dataset_id}/risk-summary",
    response_model=RiskSummaryResponse,
)
def get_risk_summary(
    dataset_id: int,
    db: Session = Depends(get_db),
):
    _get_dataset_or_404(dataset_id, db)
    return build_risk_summary(dataset_id, db)