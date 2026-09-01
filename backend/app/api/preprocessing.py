from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.db.database import get_db
from app.models.dataset import Dataset
from app.models.user import User, UserRole
from app.schemas.preprocessing import (
    FeaturesResponse,
    PreprocessingSummary,
    QualityReportResponse,
)
from app.services.preprocessing_service import (
    get_quality_report,
    preprocess_dataset,
)


router = APIRouter(
    prefix="/datasets",
    tags=["preprocessing"],
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


def _get_result_or_404(dataset_id: int, db: Session):
    result = get_quality_report(dataset_id, db)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No preprocessing report is available for this dataset.",
        )
    return result


@router.post(
    "/{dataset_id}/preprocess",
    response_model=PreprocessingSummary,
)
def preprocess_dataset_endpoint(
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
        result = preprocess_dataset(dataset, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Processed dataset could not be stored.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dataset preprocessing failed.",
        ) from exc
    return {
        "dataset_id": result.dataset_id,
        "processing_status": result.processing_status,
        "processed_at": result.processed_at,
        "quality_report": result.quality_report,
        "generated_features": result.generated_features,
    }


@router.get(
    "/{dataset_id}/quality-report",
    response_model=QualityReportResponse,
)
def dataset_quality_report(dataset_id: int, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    result = _get_result_or_404(dataset_id, db)
    return {
        "dataset_id": result.dataset_id,
        "processing_status": result.processing_status,
        "processed_at": result.processed_at,
        "quality_report": result.quality_report,
    }


@router.get("/{dataset_id}/features", response_model=FeaturesResponse)
def dataset_features(dataset_id: int, db: Session = Depends(get_db)):
    _get_dataset_or_404(dataset_id, db)
    result = _get_result_or_404(dataset_id, db)
    return {
        "dataset_id": result.dataset_id,
        "processing_status": result.processing_status,
        "processed_at": result.processed_at,
        "features": result.generated_features,
    }