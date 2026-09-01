from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.anomaly_detection import (
    AnomalyDetectionResult,
    AnomalyRiskLevel,
)
from app.models.dataset import Dataset
from app.models.dataset_processing import DatasetProcessingResult
from app.schemas.anomaly import (
    AnomalySummaryResponse,
    DetectionSummaryResponse,
    ModelConfiguration,
    TopContributingFeature,
)
from ml.anomaly_detection.feature_selector import InsufficientFeaturesError
from ml.anomaly_detection.isolation_forest import (
    IsolationForestConfig,
    detect_anomalies,
)

# Scores are batch-normalized unusualness scores in the inclusive range 0..1.
# These levels communicate potential risk requiring review, not proof of fraud.
RISK_THRESHOLDS: tuple[tuple[float, AnomalyRiskLevel], ...] = (
    (0.75, AnomalyRiskLevel.CRITICAL),
    (0.50, AnomalyRiskLevel.HIGH),
    (0.25, AnomalyRiskLevel.MEDIUM),
    (0.00, AnomalyRiskLevel.LOW),
)


def risk_level_from_score(anomaly_score: float) -> AnomalyRiskLevel:
    """Map a normalized anomaly score to a review-oriented risk level."""
    for threshold, risk_level in RISK_THRESHOLDS:
        if anomaly_score >= threshold:
            return risk_level
    return AnomalyRiskLevel.LOW


def _processed_path(
    dataset: Dataset,
    processing_result: DatasetProcessingResult | None,
) -> Path:
    if processing_result is None or not processing_result.processed_filename:
        raise ValueError(
            "This dataset has not been preprocessed. "
            "Run preprocessing before anomaly detection."
        )
    path = Path(settings.processed_uploads_dir) / processing_result.processed_filename
    if not path.exists():
        raise ValueError("The processed dataset file is missing.")
    return path


def _load_processed_dataframe(
    dataset: Dataset,
    processing_result: DatasetProcessingResult | None,
) -> pd.DataFrame:
    path = _processed_path(dataset, processing_result)
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ValueError("The processed dataset could not be loaded as CSV.") from exc


def _model_config(contamination: float | None = None) -> IsolationForestConfig:
    return IsolationForestConfig(
        contamination=(
            contamination
            if contamination is not None
            else settings.anomaly_contamination
        ),
        random_state=settings.anomaly_random_state,
        n_estimators=settings.anomaly_n_estimators,
    )


def _row_identifier(position: int) -> str:
    """Use a stable one-based data-row identifier for the processed CSV."""
    return f"row-{position + 1}"


def _as_json_features(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "feature": item["feature"],
            "value": float(item["value"]),
            "mean": float(item["mean"]),
            "standard_deviation": float(item["standard_deviation"]),
            "z_score": float(item["z_score"]),
            "deviation_direction": item["deviation_direction"],
        }
        for item in value
    ]


def detect_and_store_anomalies(
    dataset: Dataset,
    db: Session,
    *,
    contamination: float | None = None,
) -> DetectionSummaryResponse:
    processing_result = db.scalar(
        select(DatasetProcessingResult).where(
            DatasetProcessingResult.dataset_id == dataset.id
        )
    )
    dataframe = _load_processed_dataframe(dataset, processing_result)
    config = _model_config(contamination)
    detection = detect_anomalies(dataframe, config=config)
    detected_at = datetime.now(timezone.utc)

    records: list[AnomalyDetectionResult] = []
    for position, (_, result_row) in enumerate(detection.results.iterrows()):
        score = float(result_row["anomaly_score"])
        records.append(
            AnomalyDetectionResult(
                dataset_id=dataset.id,
                row_identifier=_row_identifier(position),
                anomaly_detected=bool(result_row["anomaly_detected"]),
                anomaly_score=score,
                risk_level=risk_level_from_score(score),
                contributing_features=_as_json_features(
                    result_row["top_contributing_features"]
                ),
                explanation=result_row["anomaly_explanation"],
                detected_at=detected_at,
            )
        )

    # A detection request represents the latest run for this dataset.
    db.execute(
        delete(AnomalyDetectionResult).where(
            AnomalyDetectionResult.dataset_id == dataset.id
        )
    )
    db.add_all(records)
    db.commit()

    total_records = len(records)
    total_anomalies = sum(record.anomaly_detected for record in records)
    anomaly_percentage = (
        round((total_anomalies / total_records) * 100, 2)
        if total_records
        else 0.0
    )
    return DetectionSummaryResponse(
        dataset_id=dataset.id,
        total_records_analyzed=total_records,
        total_anomalies_detected=total_anomalies,
        anomaly_percentage=anomaly_percentage,
        features_used=detection.feature_names,
        model_configuration=ModelConfiguration(
            contamination=config.contamination,
            random_state=config.random_state,
            n_estimators=config.n_estimators,
        ),
    )


def list_anomalies(
    dataset_id: int,
    db: Session,
    *,
    page: int,
    page_size: int,
    anomaly_detected: bool | None,
    risk_level: AnomalyRiskLevel | None,
) -> tuple[list[AnomalyDetectionResult], int]:
    filters = [AnomalyDetectionResult.dataset_id == dataset_id]
    if anomaly_detected is not None:
        filters.append(
            AnomalyDetectionResult.anomaly_detected == anomaly_detected
        )
    if risk_level is not None:
        filters.append(AnomalyDetectionResult.risk_level == risk_level)

    total = db.scalar(
        select(func.count(AnomalyDetectionResult.id)).where(*filters)
    ) or 0
    results = list(
        db.scalars(
            select(AnomalyDetectionResult)
            .where(*filters)
            .order_by(
                AnomalyDetectionResult.anomaly_detected.desc(),
                AnomalyDetectionResult.anomaly_score.desc(),
                AnomalyDetectionResult.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return results, int(total)


def build_anomaly_summary(
    dataset_id: int,
    db: Session,
) -> AnomalySummaryResponse:
    results = list(
        db.scalars(
            select(AnomalyDetectionResult)
            .where(AnomalyDetectionResult.dataset_id == dataset_id)
            .order_by(AnomalyDetectionResult.id)
        ).all()
    )
    total_records = len(results)
    total_anomalies = sum(result.anomaly_detected for result in results)
    risk_distribution = {
        risk_level: sum(
            result.risk_level == risk_level for result in results
        )
        for risk_level in AnomalyRiskLevel
    }
    feature_counts: dict[str, int] = defaultdict(int)
    feature_z_scores: dict[str, list[float]] = defaultdict(list)
    for result in results:
        if not result.anomaly_detected:
            continue
        for feature in result.contributing_features:
            name = feature.get("feature")
            if not name:
                continue
            feature_counts[name] += 1
            feature_z_scores[name].append(abs(float(feature.get("z_score", 0))))

    top_features = sorted(
        (
            TopContributingFeature(
                feature=name,
                anomaly_count=count,
                average_absolute_z_score=round(
                    sum(feature_z_scores[name]) / len(feature_z_scores[name]),
                    6,
                ),
            )
            for name, count in feature_counts.items()
        ),
        key=lambda item: (
            item.anomaly_count,
            item.average_absolute_z_score,
        ),
        reverse=True,
    )[:5]
    anomaly_percentage = (
        round((total_anomalies / total_records) * 100, 2)
        if total_records
        else 0.0
    )
    return AnomalySummaryResponse(
        dataset_id=dataset_id,
        total_records_analyzed=total_records,
        total_anomalies=total_anomalies,
        normal_records=total_records - total_anomalies,
        anomaly_percentage=anomaly_percentage,
        risk_level_distribution=risk_distribution,
        top_contributing_features=top_features,
    )