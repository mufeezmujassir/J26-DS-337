"""Shared evaluation helpers for the disruption-detection classifiers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

from app.replanning.disruption_detection.classifiers import (
    FEATURE_NAMES,
    LABEL_DISRUPTION,
    SEVERITY_LEVELS,
    row_to_signals,
)
from app.replanning.disruption_detection.fusion import FusionEngine
from app.replanning.disruption_detection.severity_classifier import (
    classify_severity,
)
from app.replanning.disruption_detection.trigger_rules import apply_rules

LOGGER = logging.getLogger(__name__)

PredictionRecord = Dict[str, Any]


def features_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return the 13 model features as a name-keyed mapping."""
    return {name: row.get(name, 0.0) for name in FEATURE_NAMES}


def run_rules(
    row: Dict[str, Any], engine: FusionEngine
) -> Dict[str, Any]:
    """Run the existing rule-based engine on a single dataset row."""
    signals = row_to_signals(row)
    triggered = apply_rules(signals)
    fused = engine.fuse(signals)
    return {
        "pred_label": 1 if triggered else 0,
        "prob": float(fused["score"]),
        "pred_severity": classify_severity(triggered),
        "rule_names": [rule.get("name", "") for rule in triggered],
    }


def run_ml(
    row: Dict[str, Any], classifier: Any
) -> Dict[str, Any]:
    """Run the ML classifiers on a single dataset row."""
    features = features_from_row(row)
    prediction = classifier.predict(features)
    return {
        "pred_label": 1 if prediction["is_disruption"] else 0,
        "prob": float(prediction["probability"]),
        "pred_severity": prediction["severity"],
        "severity_confidence": float(prediction.get("confidence", 0.0)),
    }


def run_hybrid(
    row: Dict[str, Any], classifier: Any, engine: FusionEngine
) -> Dict[str, Any]:
    """Run the hybrid (rules + ML) pipeline on a single dataset row."""
    features = features_from_row(row)
    ml_prediction = classifier.predict(features)
    signals = row_to_signals(row)
    triggered = apply_rules(signals)
    decision = engine.fuse_hybrid(triggered, ml_prediction)
    return {
        "pred_label": 1 if decision["is_disruption"] else 0,
        "prob": float(ml_prediction["probability"]),
        "pred_severity": decision["severity"],
        "decision": decision["decision"],
        "requires_confirmation": decision["requires_confirmation"],
        "detected_by": decision["detected_by"],
    }


def make_record(
    row: Dict[str, Any], prediction: Dict[str, Any]
) -> PredictionRecord:
    """Merge a prediction with the ground truth into a single record."""
    record: PredictionRecord = {
        "true_label": true_label(row),
        "pred_label": int(prediction["pred_label"]),
        "prob": float(prediction["prob"]),
        "true_severity": true_severity(row),
        "pred_severity": prediction["pred_severity"],
    }
    for key in (
        "rule_names",
        "severity_confidence",
        "decision",
        "requires_confirmation",
        "detected_by",
    ):
        if key in prediction:
            record[key] = prediction[key]
    return record


def true_label(row: Dict[str, Any]) -> int:
    """Return the binary ground-truth label (1 = disruption)."""
    return 1 if row.get("label") == LABEL_DISRUPTION else 0


def true_severity(row: Dict[str, Any]) -> str:
    """Return the ground-truth severity for a dataset row."""
    return str(row.get("severity", "none"))


def presence_metrics(
    records: Sequence[PredictionRecord],
) -> Dict[str, Any]:
    """Compute binary presence metrics from per-row records."""
    y_true = np.asarray([record["true_label"] for record in records], dtype=int)
    y_pred = np.asarray([record["pred_label"] for record in records], dtype=int)
    y_prob = np.asarray([record["prob"] for record in records], dtype=float)

    metrics: Dict[str, Any] = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(
            float(precision_score(y_true, y_pred, zero_division=0)), 4
        ),
        "recall": round(
            float(recall_score(y_true, y_pred, zero_division=0)), 4
        ),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "support": {
            "total": int(len(records)),
            "positive": int(y_true.sum()),
            "negative": int((y_true == 0).sum()),
        },
    }

    if len(set(y_true.tolist())) > 1:
        metrics["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 4)
    else:
        metrics["roc_auc"] = None
        LOGGER.warning("ROC-AUC undefined: only one class present")

    return metrics


def severity_metrics(
    records: Sequence[PredictionRecord],
) -> Dict[str, Any]:
    """Compute severity metrics on detected true disruptions."""
    labels = list(SEVERITY_LEVELS)
    subset = [
        record
        for record in records
        if record["true_label"] == 1 and record["pred_label"] == 1
    ]

    if not subset:
        return {"support": 0, "note": "no correctly detected disruptions"}

    y_true = [record["true_severity"] for record in subset]
    y_pred = [record["pred_severity"] for record in subset]

    matrix = confusion_matrix(y_true, y_pred, labels=labels)

    per_class: Dict[str, Dict[str, float]] = {}
    precision = precision_score(
        y_true, y_pred, labels=labels, average=None, zero_division=0
    )
    recall = recall_score(
        y_true, y_pred, labels=labels, average=None, zero_division=0
    )
    f1 = f1_score(
        y_true, y_pred, labels=labels, average=None, zero_division=0
    )
    for index, level in enumerate(labels):
        per_class[level] = {
            "precision": round(float(precision[index]), 4),
            "recall": round(float(recall[index]), 4),
            "f1": round(float(f1[index]), 4),
            "support": int(matrix[index].sum()),
        }

    return {
        "support": len(subset),
        "labels": labels,
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(
            float(
                f1_score(
                    y_true,
                    y_pred,
                    labels=labels,
                    average="macro",
                    zero_division=0,
                )
            ),
            4,
        ),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
    }


def build_result(
    variant: str,
    records: Sequence[PredictionRecord],
    **extra: Any,
) -> Dict[str, Any]:
    """Bundle presence + severity metrics for a variant into one payload."""
    payload: Dict[str, Any] = {
        "variant": variant,
        "n_samples": len(records),
        "presence": presence_metrics(records),
        "severity": severity_metrics(records),
        "curves": curve_data(records),
    }
    payload.update(extra)
    return payload


def curve_data(records: Sequence[PredictionRecord]) -> Dict[str, Any]:
    """Return ROC and precision-recall curve points for plotting."""
    y_true = np.asarray([record["true_label"] for record in records], dtype=int)
    y_prob = np.asarray([record["prob"] for record in records], dtype=float)

    if len(set(y_true.tolist())) < 2:
        return {}

    fpr, tpr, _ = roc_curve(y_true, y_prob)
    precision, recall, _ = precision_recall_curve(y_true, y_prob)

    return {
        "roc": {
            "fpr": [round(float(value), 4) for value in fpr],
            "tpr": [round(float(value), 4) for value in tpr],
        },
        "pr": {
            "precision": [round(float(value), 4) for value in precision],
            "recall": [round(float(value), 4) for value in recall],
        },
    }


def save_result(path: str | Path, payload: Dict[str, Any]) -> Path:
    """Write a result payload to ``path`` as pretty JSON."""
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Saved results to %s", resolved)
    return resolved


def summary_table(payload: Dict[str, Any]) -> str:
    """Render a compact text summary of a result payload."""
    presence = payload.get("presence", {})
    severity = payload.get("severity", {})
    lines = [
        f"Variant: {payload.get('variant', '?')}",
        f"  Samples         : {payload.get('n_samples', '?')}",
        "  Presence:",
        f"    accuracy      : {presence.get('accuracy')}",
        f"    precision     : {presence.get('precision')}",
        f"    recall        : {presence.get('recall')}",
        f"    f1            : {presence.get('f1')}",
        f"    roc_auc       : {presence.get('roc_auc')}",
        f"    confusion     : {presence.get('confusion_matrix')}",
        "  Severity:",
        f"    support       : {severity.get('support')}",
        f"    accuracy      : {severity.get('accuracy')}",
        f"    macro_f1      : {severity.get('macro_f1')}",
        f"    confusion     : {severity.get('confusion_matrix')}",
    ]
    return "\n".join(lines)


__all__ = [
    "PredictionRecord",
    "true_label",
    "true_severity",
    "features_from_row",
    "run_rules",
    "run_ml",
    "run_hybrid",
    "make_record",
    "presence_metrics",
    "severity_metrics",
    "curve_data",
    "build_result",
    "save_result",
    "summary_table",
]