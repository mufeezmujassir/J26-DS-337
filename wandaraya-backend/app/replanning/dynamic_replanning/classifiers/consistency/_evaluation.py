"""Shared evaluation helpers for the cross-turn consistency classifiers."""

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

from app.replanning.dynamic_replanning.classifiers.consistency import (
    DRIFT_TYPES,
    FEATURE_NAMES,
    LABEL_DRIFT,
)

LOGGER = logging.getLogger(__name__)

PredictionRecord = Dict[str, Any]

# Feature groups used by the source-removal ablation study.
FEATURE_GROUPS: Dict[str, tuple[str, ...]] = {
    "constraints": (
        "num_prior_constraints",
        "num_conflicting_constraints",
    ),
    "stated": (
        "last_vibe_mentioned",
        "last_budget_mentioned",
        "last_pace_preference",
    ),
    "churn": (
        "plan_changes_since_last_turn",
        "num_turns",
    ),
    "explicit_user": (
        "num_explicit_confirmations",
        "num_explicit_rejections",
    ),
    "context": (
        "avg_emotion_score",
        "time_since_last_turn_minutes",
        "num_replans_this_trip",
    ),
}


def features_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return the 12 model features as a name-keyed mapping."""
    return {name: row.get(name, 0.0) for name in FEATURE_NAMES}


def rules_drift(row: Dict[str, Any]) -> bool:
    """Apply the production hard rules; True when drift is flagged.

    Mirrors :meth:`CrossTurnConsistency.prior_constraint_violated` and the
    dataset labeler: any recorded constraint violation means drift.
    """
    return int(row.get("num_conflicting_constraints", 0)) > 0


def run_rules(row: Dict[str, Any]) -> Dict[str, Any]:
    """Run the rules-only baseline on a single dataset row."""
    drift = rules_drift(row)
    return {
        "pred_label": 1 if drift else 0,
        "prob": 1.0 if drift else 0.0,
        "pred_drift": drift,
    }


def run_ml(row: Dict[str, Any], classifier: Any) -> Dict[str, Any]:
    """Run the RF classifier on a single dataset row."""
    features = features_from_row(row)
    prediction = classifier.predict(features)
    drift = bool(prediction["drift_detected"])
    return {
        "pred_label": 1 if drift else 0,
        "prob": float(prediction["probability"]),
        "pred_drift": drift,
    }


def run_hybrid(row: Dict[str, Any], classifier: Any) -> Dict[str, Any]:
    """Run the hybrid (hard rules + RF) pipeline on a single dataset row."""
    rule_drift = rules_drift(row)
    if rule_drift:
        return {
            "pred_label": 1,
            "prob": 1.0,
            "pred_drift": True,
            "rule_drift": True,
            "detected_by": "hard_rules",
        }

    features = features_from_row(row)
    prediction = classifier.predict(features)
    drift = bool(prediction["drift_detected"])
    return {
        "pred_label": 1 if drift else 0,
        "prob": float(prediction["probability"]),
        "pred_drift": drift,
        "rule_drift": False,
        "detected_by": "rf" if drift else "none",
    }


def true_label(row: Dict[str, Any]) -> int:
    """Return the binary ground-truth label (1 = drift)."""
    return 1 if int(row.get("label", 0)) == LABEL_DRIFT else 0


def make_record(
    row: Dict[str, Any], prediction: Dict[str, Any]
) -> PredictionRecord:
    """Merge a prediction with the ground truth into a single record."""
    record: PredictionRecord = {
        "true_label": true_label(row),
        "pred_label": int(prediction["pred_label"]),
        "prob": float(prediction["prob"]),
        "intended_drift_type": str(row.get("intended_drift_type", "none")),
    }
    for key in ("pred_drift", "rule_drift", "detected_by"):
        if key in prediction:
            record[key] = prediction[key]
    return record


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
            "positive_drift": int(y_true.sum()),
            "negative_consistent": int((y_true == 0).sum()),
        },
    }

    if len(set(y_true.tolist())) > 1:
        metrics["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 4)
    else:
        metrics["roc_auc"] = None
        LOGGER.warning("ROC-AUC undefined: only one class present")

    return metrics


def drift_type_metrics(
    records: Sequence[PredictionRecord],
) -> Dict[str, Dict[str, Any]]:
    """Compute detection rate per construction drift type.

    Rows labelled ``consistent`` are excluded. ``recall`` here is how often
    the variant flags a row built with that drift type as drifted.
    """
    per_type: Dict[str, Dict[str, Any]] = {}
    for drift_type in DRIFT_TYPES:
        subset = [
            record
            for record in records
            if record["true_label"] == 1
            and record.get("intended_drift_type") == drift_type
        ]
        if not subset:
            continue
        detected = sum(1 for record in subset if record["pred_label"] == 1)
        per_type[drift_type] = {
            "support": len(subset),
            "detected": int(detected),
            "recall": round(detected / len(subset), 4),
        }
    return per_type


def curve_data(records: Sequence[PredictionRecord]) -> Dict[str, Any]:
    """Return ROC and precision-recall curve points."""
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


def build_result(
    variant: str,
    records: Sequence[PredictionRecord],
    **extra: Any,
) -> Dict[str, Any]:
    """Bundle presence + per-drift-type metrics for a variant."""
    payload: Dict[str, Any] = {
        "variant": variant,
        "n_samples": len(records),
        "presence": presence_metrics(records),
        "per_drift_type": drift_type_metrics(records),
        "curves": curve_data(records),
    }
    payload.update(extra)
    return payload


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
    lines = [
        f"Variant: {payload.get('variant', '?')}",
        f"  Samples         : {payload.get('n_samples', '?')}",
        "  Presence (positive = drift):",
        f"    accuracy      : {presence.get('accuracy')}",
        f"    precision     : {presence.get('precision')}",
        f"    recall        : {presence.get('recall')}",
        f"    f1            : {presence.get('f1')}",
        f"    roc_auc       : {presence.get('roc_auc')}",
        f"    confusion     : {presence.get('confusion_matrix')}",
        "  Per drift type (recall):",
    ]
    for drift_type, entry in (payload.get("per_drift_type") or {}).items():
        lines.append(
            f"    {drift_type:<36}: {entry['recall']} "
            f"({entry['detected']}/{entry['support']})"
        )
    return "\n".join(lines)


__all__ = [
    "PredictionRecord",
    "FEATURE_GROUPS",
    "features_from_row",
    "rules_drift",
    "run_rules",
    "run_ml",
    "run_hybrid",
    "true_label",
    "make_record",
    "presence_metrics",
    "drift_type_metrics",
    "curve_data",
    "build_result",
    "save_result",
    "summary_table",
]
