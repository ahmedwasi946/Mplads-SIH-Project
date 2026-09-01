from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.dataset_processing import DatasetProcessingStatus


class FeatureAvailability(BaseModel):
    name: str
    description: str
    available: bool
    source_columns: list[str]


class DataQualityReport(BaseModel):
    total_rows: int = Field(ge=0)
    total_columns: int = Field(ge=0)
    columns: list[str]
    required_columns: dict[str, str | None]
    columns_used: list[str]
    columns_unavailable: list[str]
    missing_values_by_column: dict[str, int]
    missing_values_after_preprocessing_by_column: dict[str, int]
    duplicate_rows: int = Field(ge=0)
    duplicates_removed: int = Field(ge=0)
    invalid_numeric_values: dict[str, int]
    invalid_date_values: dict[str, int]
    invalid_row_count: int = Field(ge=0)
    invalid_row_indices: list[int]
    numeric_imputations: dict[str, int]
    categorical_imputations: dict[str, int]
    successfully_generated_features: list[str]


class PreprocessingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: int
    processing_status: DatasetProcessingStatus
    processed_at: datetime
    quality_report: DataQualityReport
    generated_features: list[FeatureAvailability]


class QualityReportResponse(BaseModel):
    dataset_id: int
    processing_status: DatasetProcessingStatus
    processed_at: datetime
    quality_report: DataQualityReport


class FeaturesResponse(BaseModel):
    dataset_id: int
    processing_status: DatasetProcessingStatus
    processed_at: datetime
    features: list[FeatureAvailability]