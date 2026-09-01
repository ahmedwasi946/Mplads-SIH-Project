from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.dataset import DatasetUploadStatus


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_name: str
    original_filename: str
    file_type: str
    file_size: int = Field(ge=0)
    total_rows: int = Field(ge=0)
    total_columns: int = Field(ge=0)
    upload_status: DatasetUploadStatus
    uploaded_at: datetime


class DatasetPreviewResponse(BaseModel):
    dataset: DatasetResponse
    columns: list[str]
    rows: list[dict[str, str]]