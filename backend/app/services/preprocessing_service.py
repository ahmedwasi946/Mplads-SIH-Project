from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.dataset import Dataset
from app.models.dataset_processing import (
    DatasetProcessingResult,
    DatasetProcessingStatus,
)
from ml.preprocessing.data_preprocessor import preprocess_dataframe


def get_processed_upload_directory() -> Path:
    directory = Path(settings.processed_uploads_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def create_processed_filename() -> str:
    return f"{uuid4().hex}.csv"


def _read_original_dataset(dataset: Dataset) -> pd.DataFrame:
    original_path = Path(settings.uploads_dir) / dataset.stored_filename
    try:
        return pd.read_csv(original_path, dtype=object)
    except FileNotFoundError as exc:
        raise ValueError("The original uploaded dataset file is missing.") from exc
    except pd.errors.EmptyDataError as exc:
        return pd.DataFrame()
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ValueError("The uploaded dataset could not be parsed as CSV.") from exc


def preprocess_dataset(
    dataset: Dataset,
    db: Session,
) -> DatasetProcessingResult:
    dataframe = _read_original_dataset(dataset)
    result = preprocess_dataframe(dataframe, remove_duplicates=True)
    processed_filename = create_processed_filename()
    processed_path = get_processed_upload_directory() / processed_filename
    old_processed_filename: str | None = None
    try:
        result.dataframe.to_csv(processed_path, index=False, date_format="%Y-%m-%d")
        processing_result = db.scalar(
            select(DatasetProcessingResult).where(
                DatasetProcessingResult.dataset_id == dataset.id
            )
        )
        if processing_result is None:
            processing_result = DatasetProcessingResult(
                dataset_id=dataset.id,
                processing_status=DatasetProcessingStatus.PROCESSED,
                quality_report=result.quality_report,
                generated_features=result.feature_result.feature_availability,
                processed_filename=processed_filename,
            )
            db.add(processing_result)
        else:
            old_processed_filename = processing_result.processed_filename
            processing_result.processing_status = (
                DatasetProcessingStatus.PROCESSED
            )
            processing_result.quality_report = result.quality_report
            processing_result.generated_features = (
                result.feature_result.feature_availability
            )
            processing_result.processed_filename = processed_filename
        db.commit()
        db.refresh(processing_result)
    except Exception:
        db.rollback()
        processed_path.unlink(missing_ok=True)
        raise

    if old_processed_filename and old_processed_filename != processed_filename:
        (
            get_processed_upload_directory() / old_processed_filename
        ).unlink(missing_ok=True)
    return processing_result


def get_quality_report(
    dataset_id: int,
    db: Session,
) -> DatasetProcessingResult | None:
    return db.scalar(
        select(DatasetProcessingResult).where(
            DatasetProcessingResult.dataset_id == dataset_id
        )
    )


def remove_processed_file(filename: str | None) -> None:
    if filename:
        (get_processed_upload_directory() / filename).unlink(missing_ok=True)