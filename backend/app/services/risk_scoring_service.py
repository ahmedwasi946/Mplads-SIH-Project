from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.anomaly_detection import AnomalyDetectionResult
from app.models.dataset import Dataset
from app.models.dataset_processing import DatasetProcessingResult
from app.models.risk_assessment import RiskAssessment, RiskAssessmentLevel
from app.schemas.risk import RiskSummaryResponse, TopRiskFactor
from ml.preprocessing.data_preprocessor import identify_columns


RISK_LEVEL_THRESHOLDS: tuple[tuple[float, RiskAssessmentLevel], ...] = (
    (76.0, RiskAssessmentLevel.CRITICAL),
    (51.0, RiskAssessmentLevel.HIGH),
    (26.0, RiskAssessmentLevel.MEDIUM),
    (0.0, RiskAssessmentLevel.LOW),
)

GROUP_WEIGHTS: dict[str, float] = {
    "anomaly_signal": 0.35,
    "financial_irregularity": 0.25,
    "project_delay": 0.20,
    "progress_expenditure_mismatch": 0.20,
}


@dataclass(frozen=True)
class SignalDefinition:
    group: str
    label: str


SIGNAL_DEFINITIONS: dict[str, SignalDefinition] = {
    "anomaly_score": SignalDefinition("anomaly_signal", "anomaly score"),
    "anomaly_detected": SignalDefinition(
        "anomaly_signal", "anomaly detected status"
    ),
    "cost_variance_percentage": SignalDefinition(
        "financial_irregularity", "cost variance percentage"
    ),
    "fund_utilization_deviation": SignalDefinition(
        "financial_irregularity", "fund utilization deviation"
    ),
    "project_delay_days": SignalDefinition("project_delay", "project delay"),
    "project_status": SignalDefinition("project_delay", "project status"),
    "progress_expenditure_gap": SignalDefinition(
        "progress_expenditure_mismatch", "progress-expenditure gap"
    ),
}


def risk_level_from_score(score: float) -> RiskAssessmentLevel:
    for threshold, level in RISK_LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return RiskAssessmentLevel.LOW


def _processed_path(
    processing_result: DatasetProcessingResult | None,
) -> Path:
    if processing_result is None or not processing_result.processed_filename:
        raise ValueError(
            "This dataset has not been preprocessed. "
            "Run preprocessing before calculating risk."
        )
    path = Path(settings.processed_uploads_dir) / processing_result.processed_filename
    if not path.exists():
        raise ValueError("The processed dataset file is missing.")
    return path


def _load_processed_dataframe(
    processing_result: DatasetProcessingResult | None,
) -> pd.DataFrame:
    try:
        return pd.read_csv(_processed_path(processing_result))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ValueError("The processed dataset could not be loaded as CSV.") from exc


def _numeric_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(dataframe[column], errors="coerce")
    return values.replace([np.inf, -np.inf], np.nan).astype(float)


def _find_column(
    dataframe: pd.DataFrame,
    column_map: dict[str, str | None],
    canonical_name: str,
) -> str | None:
    if canonical_name in dataframe.columns:
        return canonical_name
    return column_map.get(canonical_name)


def _add_signal(
    signals: dict[str, pd.Series],
    name: str,
    values: pd.Series,
) -> None:
    values = values.replace([np.inf, -np.inf], np.nan).astype(float)
    if values.notna().any():
        signals[name] = values


def _build_signal_frame(
    dataframe: pd.DataFrame,
    anomaly_results: list[AnomalyDetectionResult],
) -> dict[str, pd.Series]:
    column_map = identify_columns(list(dataframe.columns))
    signals: dict[str, pd.Series] = {}

    anomaly_by_row = {result.row_identifier: result for result in anomaly_results}
    anomaly_scores = pd.Series(np.nan, index=dataframe.index, dtype="float64")
    anomaly_status = pd.Series(np.nan, index=dataframe.index, dtype="float64")
    for position, index in enumerate(dataframe.index):
        result = anomaly_by_row.get(f"row-{position + 1}")
        if result is not None:
            anomaly_scores.loc[index] = float(result.anomaly_score)
            anomaly_status.loc[index] = 1.0 if result.anomaly_detected else 0.0
    _add_signal(signals, "anomaly_score", anomaly_scores.clip(lower=0, upper=1))
    _add_signal(signals, "anomaly_detected", anomaly_status)

    estimated = _find_column(dataframe, column_map, "estimated_cost")
    actual = _find_column(dataframe, column_map, "actual_expenditure")
    cost_variance = (
        _numeric_series(dataframe, "cost_variance_percentage")
        if "cost_variance_percentage" in dataframe.columns
        else None
    )
    if cost_variance is None and estimated and actual:
        estimated_values = _numeric_series(dataframe, estimated).replace(0, np.nan)
        actual_values = _numeric_series(dataframe, actual)
        cost_variance = ((actual_values - estimated_values) / estimated_values) * 100
    if cost_variance is not None:
        _add_signal(
            signals,
            "cost_variance_percentage",
            cost_variance.abs(),
        )

    sanctioned = _find_column(dataframe, column_map, "sanctioned_amount")
    utilized = _find_column(dataframe, column_map, "utilized_amount")
    fund_utilization = (
        _numeric_series(dataframe, "fund_utilization_percentage")
        if "fund_utilization_percentage" in dataframe.columns
        else None
    )
    if fund_utilization is None and sanctioned and utilized:
        sanctioned_values = _numeric_series(dataframe, sanctioned).replace(0, np.nan)
        utilized_values = _numeric_series(dataframe, utilized)
        fund_utilization = (utilized_values / sanctioned_values) * 100
    if fund_utilization is not None:
        _add_signal(
            signals,
            "fund_utilization_deviation",
            (fund_utilization - 100).abs(),
        )

    delay_column = _find_column(dataframe, column_map, "project_delay_days")
    if delay_column:
        _add_signal(
            signals,
            "project_delay_days",
            _numeric_series(dataframe, delay_column).clip(lower=0),
        )

    status_column = _find_column(dataframe, column_map, "project_status")
    if status_column:
        normalized_status = (
            dataframe[status_column]
            .astype("string")
            .str.strip()
            .str.lower()
        )
        _add_signal(
            signals,
            "project_status",
            (~normalized_status.isin({"completed", "complete"}))
            .astype(float),
        )

    gap_column = _find_column(dataframe, column_map, "progress_expenditure_gap")
    if gap_column:
        _add_signal(
            signals,
            "progress_expenditure_gap",
            _numeric_series(dataframe, gap_column).abs(),
        )

    return signals


def _normalize_signal(values: pd.Series) -> pd.Series:
    finite = values.dropna()
    normalized = pd.Series(np.nan, index=values.index, dtype="float64")
    if finite.empty:
        return normalized
    minimum = float(finite.min())
    maximum = float(finite.max())
    if maximum == minimum:
        normalized.loc[finite.index] = 1.0 if maximum > 0 else 0.0
    else:
        normalized.loc[finite.index] = (
            (finite - minimum) / (maximum - minimum)
        ).clip(0, 1)
    return normalized


def _display_factor_value(signal: str, value: float) -> float | str:
    if signal == "anomaly_detected":
        return "Detected" if value >= 1 else "Normal"
    if signal == "project_status":
        return "Incomplete or ongoing" if value >= 1 else "Completed"
    if signal == "project_delay_days":
        return round(value, 2)
    return round(value, 2)


def _factor_explanation(
    level: RiskAssessmentLevel,
    factors: list[dict[str, Any]],
) -> str | None:
    if level not in {RiskAssessmentLevel.HIGH, RiskAssessmentLevel.CRITICAL}:
        return None
    if not factors:
        return (
            f"{level.value} risk requires manual review, but no contributing "
            "signal detail was available."
        )
    descriptions: list[str] = []
    for factor in factors[:3]:
        signal = factor["signal"]
        label = factor["label"]
        value = factor["value"]
        if signal == "anomaly_score":
            descriptions.append(f"strong anomaly score ({float(value):.2f})")
        elif signal == "anomaly_detected":
            descriptions.append("anomaly detection marked the record for review")
        elif signal == "cost_variance_percentage":
            descriptions.append(f"cost variance of {float(value):.2f}%")
        elif signal == "fund_utilization_deviation":
            descriptions.append(
                f"fund utilization deviation of {float(value):.2f} percentage points"
            )
        elif signal == "project_delay_days":
            descriptions.append(f"project delay of {float(value):.0f} days")
        elif signal == "project_status":
            descriptions.append("an incomplete or ongoing project status")
        elif signal == "progress_expenditure_gap":
            descriptions.append(
                f"progress-expenditure gap of {float(value):.2f} percentage points"
            )
        else:
            descriptions.append(label)
    if len(descriptions) == 1:
        reason = descriptions[0]
    elif len(descriptions) == 2:
        reason = f"{descriptions[0]} and {descriptions[1]}"
    else:
        reason = f"{', '.join(descriptions[:-1])}, and {descriptions[-1]}"
    return (
        f"{level.value} risk due to {reason}. "
        "This score is a decision-support indicator and requires manual review."
    )


def _risk_factors_for_row(
    normalized_signals: dict[str, pd.Series],
    raw_signals: dict[str, pd.Series],
    index: Any,
) -> tuple[float, list[dict[str, Any]]]:
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for signal, values in normalized_signals.items():
        value = values.loc[index]
        if pd.notna(value):
            grouped[SIGNAL_DEFINITIONS[signal].group].append((signal, float(value)))

    available_groups = [
        group for group, values in grouped.items() if values
    ]
    total_weight = sum(GROUP_WEIGHTS[group] for group in available_groups)
    if total_weight == 0:
        return 0.0, []

    score = 0.0
    factors: list[dict[str, Any]] = []
    for group, values in grouped.items():
        effective_weight = GROUP_WEIGHTS[group] / total_weight
        signal_share = effective_weight / len(values)
        for signal, normalized_value in values:
            contribution = normalized_value * signal_share * 100
            score += contribution
            if normalized_value <= 0:
                continue
            raw_value = float(raw_signals[signal].loc[index])
            factors.append(
                {
                    "signal": signal,
                    "label": SIGNAL_DEFINITIONS[signal].label,
                    "value": _display_factor_value(signal, raw_value),
                    "normalized_value": round(normalized_value, 6),
                    "contribution": round(contribution, 6),
                }
            )
    factors.sort(key=lambda factor: factor["contribution"], reverse=True)
    return round(float(score), 6), factors[:5]


def build_risk_summary(
    dataset_id: int,
    db: Session,
) -> RiskSummaryResponse:
    results = list(
        db.scalars(
            select(RiskAssessment)
            .where(RiskAssessment.dataset_id == dataset_id)
            .order_by(RiskAssessment.id)
        ).all()
    )
    total = len(results)
    distribution = {
        level: sum(result.risk_level == level for result in results)
        for level in RiskAssessmentLevel
    }
    factor_contributions: dict[str, list[float]] = defaultdict(list)
    for result in results:
        for factor in result.contributing_factors:
            label = factor.get("label")
            if label:
                factor_contributions[label].append(
                    float(factor.get("contribution", 0))
                )
    top_factors = sorted(
        (
            TopRiskFactor(
                factor=label,
                occurrence_count=len(contributions),
                average_contribution=round(
                    sum(contributions) / len(contributions), 6
                ),
            )
            for label, contributions in factor_contributions.items()
        ),
        key=lambda item: (item.occurrence_count, item.average_contribution),
        reverse=True,
    )[:5]
    available_signals = sorted(factor_contributions)
    return RiskSummaryResponse(
        dataset_id=dataset_id,
        total_records_assessed=total,
        average_risk_score=round(
            sum(float(result.overall_risk_score) for result in results) / total,
            2,
        )
        if total
        else 0.0,
        risk_level_distribution=distribution,
        high_risk_count=distribution[RiskAssessmentLevel.HIGH],
        critical_risk_count=distribution[RiskAssessmentLevel.CRITICAL],
        top_contributing_factors=top_factors,
        available_signals=available_signals,
    )


def calculate_and_store_risk(
    dataset: Dataset,
    db: Session,
) -> RiskSummaryResponse:
    processing_result = db.scalar(
        select(DatasetProcessingResult).where(
            DatasetProcessingResult.dataset_id == dataset.id
        )
    )
    dataframe = _load_processed_dataframe(processing_result)
    anomaly_results = list(
        db.scalars(
            select(AnomalyDetectionResult)
            .where(AnomalyDetectionResult.dataset_id == dataset.id)
        ).all()
    )
    raw_signals = _build_signal_frame(dataframe, anomaly_results)
    normalized_signals = {
        signal: _normalize_signal(values)
        for signal, values in raw_signals.items()
    }
    assessed_at = datetime.now(timezone.utc)
    assessments: list[RiskAssessment] = []
    for position, index in enumerate(dataframe.index):
        score, factors = _risk_factors_for_row(
            normalized_signals,
            raw_signals,
            index,
        )
        level = risk_level_from_score(score)
        assessments.append(
            RiskAssessment(
                dataset_id=dataset.id,
                row_identifier=f"row-{position + 1}",
                overall_risk_score=score,
                risk_level=level,
                contributing_factors=factors,
                explanation=_factor_explanation(level, factors),
                assessed_at=assessed_at,
            )
        )

    db.execute(
        delete(RiskAssessment).where(RiskAssessment.dataset_id == dataset.id)
    )
    db.add_all(assessments)
    db.commit()
    return build_risk_summary(dataset.id, db)


def list_risk_assessments(
    dataset_id: int,
    db: Session,
    *,
    page: int,
    page_size: int,
    risk_level: RiskAssessmentLevel | None,
) -> tuple[list[RiskAssessment], int]:
    filters = [RiskAssessment.dataset_id == dataset_id]
    if risk_level is not None:
        filters.append(RiskAssessment.risk_level == risk_level)
    total = db.scalar(
        select(func.count(RiskAssessment.id)).where(*filters)
    ) or 0
    results = list(
        db.scalars(
            select(RiskAssessment)
            .where(*filters)
            .order_by(
                RiskAssessment.overall_risk_score.desc(),
                RiskAssessment.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return results, int(total)