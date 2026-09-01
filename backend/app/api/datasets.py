from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.db.database import get_db
from app.models.dataset import Dataset, DatasetUploadStatus
from app.models.dataset_processing import DatasetProcessingResult
from app.models.user import User, UserRole
from app.services.preprocessing_service import remove_processed_file
from app.schemas.dataset import DatasetPreviewResponse, DatasetResponse
from app.services.dataset_service import (
    create_stored_filename,
    get_upload_directory,
    parse_csv_contents,
    parse_csv_file,
    remove_uploaded_file,
    save_uploaded_file,
)


router = APIRouter(
    prefix="/datasets",
    tags=["datasets"],
    dependencies=[Depends(get_current_user)],
)


def _ensure_csv_file(file: UploadFile) -> str:
    original_filename = Path(file.filename or "").name
    if not original_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A CSV file is required.",
        )
    if Path(original_filename).suffix.lower() != ".csv":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Only CSV files are accepted.",
        )
    return original_filename


@router.post(
    "/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.GOVERNMENT_OFFICER,
            UserRole.ANALYST,
        )
    ),
):
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A CSV file is required.",
        )

    original_filename = _ensure_csv_file(file)
    contents = await file.read()
    stored_filename = create_stored_filename()

    try:
        parsed_dataset = parse_csv_contents(contents)
        save_uploaded_file(contents, stored_filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Uploaded file could not be stored.",
        ) from exc

    dataset = Dataset(
        dataset_name=Path(original_filename).stem or "Dataset",
        original_filename=original_filename,
        file_type="CSV",
        file_size=len(contents),
        total_rows=parsed_dataset.total_rows,
        total_columns=parsed_dataset.total_columns,
        upload_status=DatasetUploadStatus.PROCESSED,
        stored_filename=stored_filename,
    )
    db.add(dataset)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        remove_uploaded_file(stored_filename)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset metadata could not be saved.",
        ) from exc
    db.refresh(dataset)
    return dataset


@router.get("", response_model=list[DatasetResponse])
def list_datasets(db: Session = Depends(get_db)):
    statement = select(Dataset).order_by(desc(Dataset.uploaded_at), Dataset.id)
    return db.scalars(statement).all()


@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    return dataset


@router.get("/{dataset_id}/preview", response_model=DatasetPreviewResponse)
def preview_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    file_path = get_upload_directory() / dataset.stored_filename
    try:
        parsed_dataset = parse_csv_file(file_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return DatasetPreviewResponse(
        dataset=dataset,
        columns=parsed_dataset.columns,
        rows=parsed_dataset.rows[:10],
    )


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.GOVERNMENT_OFFICER)
    ),
):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    stored_filename = dataset.stored_filename
    processing_result = db.scalar(
        select(DatasetProcessingResult).where(
            DatasetProcessingResult.dataset_id == dataset_id
        )
    )
    processed_filename = (
        processing_result.processed_filename
        if processing_result is not None
        else None
    )
    db.delete(dataset)
    db.commit()
    remove_uploaded_file(stored_filename)
    remove_processed_file(processed_filename)