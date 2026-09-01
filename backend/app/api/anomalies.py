from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.db.database import get_db
from app.models.anomaly_detection import (
    AnomalyDetectionResult,
    AnomalyRiskLevel,
)
from app.models.dataset import Dataset
from app.models.user import User, UserRole
from app.schemas.anomaly import (
    AnomalyListResponse,
    AnomalyResultResponse,
    AnomalySummaryResponse,
    DetectionRequest,
    DetectionSummaryResponse,
)
from app.services.anomaly_service import (
    build_anomaly_summary,
    detect_and_store_anomalies,
    list_anomalies,
)
from ml.anomaly_detection.feature_selector import InsufficientFeaturesError


router = APIRouter(
    prefix="/datasets",
    tags=["anomaly-detection"],
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


def _get_result_or_404(
    dataset_id: int,
    result_id: int,
    db: Session,
):
    result = db.scalar(
        select(AnomalyDetectionResult).where(
            AnomalyDetectionResult.dataset_id == dataset_id,
            AnomalyDetectionResult.id == result_id,
        )
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anomaly result not found.",
        )
    return result


@router.post(
    "/{dataset_id}/detect-anomalies",
    response_model=DetectionSummaryResponse,
)
def detect_dataset_anomalies(
    dataset_id: int,
    request: DetectionRequest | None = None,
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
        return detect_and_store_anomalies(
            dataset,
            db,
            contamination=request.contamination if request else None,
        )
    except InsufficientFeaturesError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{dataset_id}/anomalies",
    response_model=AnomalyListResponse,
)
def get_dataset_anomalies(
    dataset_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    anomaly_detected: bool | None = Query(default=None),
    risk_level: AnomalyRiskLevel | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _get_dataset_or_404(dataset_id, db)
    results, total = list_anomalies(
        dataset_id,
        db,
        page=page,
        page_size=page_size,
        anomaly_detected=anomaly_detected,
        risk_level=risk_level,
    )
    return AnomalyListResponse(
        items=results,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get(
    "/{dataset_id}/anomaly-summary",
    response_model=AnomalySummaryResponse,
)
def get_dataset_anomaly_summary(
    dataset_id: int,
    db: Session = Depends(get_db),
):
    _get_dataset_or_404(dataset_id, db)
    return build_anomaly_summary(dataset_id, db)


@router.get(
    "/{dataset_id}/anomalies/{result_id}",
    response_model=AnomalyResultResponse,
)
def get_dataset_anomaly(
    dataset_id: int,
    result_id: int,
    db: Session = Depends(get_db),
):
    _get_dataset_or_404(dataset_id, db)
    return _get_result_or_404(dataset_id, result_id, db)