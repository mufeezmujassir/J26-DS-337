"""Small serializable types used by the experimental backtesting pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class MonthlyObservation:
    month: date
    value: float | None


@dataclass(frozen=True)
class BacktestPrediction:
    origin: date
    target_month: date
    horizon: int
    actual: float
    predicted: float
    model_name: str


@dataclass
class BacktestResult:
    model_name: str
    target: str
    observation_count: int
    fold_count: int
    prediction_count: int
    metrics: dict[str, Any]
    predictions: list[BacktestPrediction]
    skipped_folds: list[dict[str, Any]] = field(default_factory=list)
    fold_metadata: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
