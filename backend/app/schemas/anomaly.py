from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.anomaly_detection import AnomalyRiskLevel


class ContributingFeature(BaseModel):
    feature: str
    value: float
    mean: float
    standard_deviation: float
    z_score: float
    deviation_direction: str


class DetectionRequest(BaseModel):
    contamination: float | None = Field(
        default=None,
        gt=0,
        le=0.5,
        description=(
            "Optional Isolation Forest contamination override. "
            "Blank uses the backend-configured default."
        ),
    )


class AnomalyResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    row_identifier: str
    anomaly_detected: bool
    anomaly_score: float = Field(ge=0, le=1)
    risk_level: AnomalyRiskLevel
    contributing_features: list[ContributingFeature]
    explanation: str | None
    detected_at: datetime


class ModelConfiguration(BaseModel):
    contamination: float | str
    random_state: int
    n_estimators: int


class DetectionSummaryResponse(BaseModel):
    dataset_id: int
    total_records_analyzed: int = Field(ge=0)
    total_anomalies_detected: int = Field(ge=0)
    anomaly_percentage: float = Field(ge=0, le=100)
    features_used: list[str]
    model_configuration: ModelConfiguration


class AnomalyListResponse(BaseModel):
    items: list[AnomalyResultResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class TopContributingFeature(BaseModel):
    feature: str
    anomaly_count: int = Field(ge=0)
    average_absolute_z_score: float = Field(ge=0)


class AnomalySummaryResponse(BaseModel):
    dataset_id: int
    total_records_analyzed: int = Field(ge=0)
    total_anomalies: int = Field(ge=0)
    normal_records: int = Field(ge=0)
    anomaly_percentage: float = Field(ge=0, le=100)
    risk_level_distribution: dict[AnomalyRiskLevel, int]
    top_contributing_features: list[TopContributingFeature]