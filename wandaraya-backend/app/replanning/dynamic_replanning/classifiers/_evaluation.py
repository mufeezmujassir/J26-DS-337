"""Shared evaluation helpers for the intent-preservation classifiers."""

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

from app.replanning.dynamic_replanning.classifiers import (
    BROKEN_TYPES,
    FEATURE_NAMES,
    LABEL_BROKEN,
    BUDGET_OVERRUN_THRESHOLD,
    LOCATION_SHIFT_THRESHOLD_KM,
    MIN_MINOR_CHANGES,
    TIME_SHIFT_THRESHOLD_MINUTES,
)
from app.replanning.dynamic_replanning.intent_preserver import (
    DECISION_BROKEN,
    DECISION_PRESERVED,
    DECISION_UNCERTAIN,
    DEFAULT_CONFIRM_THRESHOLD,
    DEFAULT_NO_PRESERVE_THRESHOLD,
    fuse_intent_decision,
)

LOGGER = logging.getLogger(__name__)

PredictionRecord = Dict[str, Any]

# Feature groups used by the source-removal ablation study.
FEATURE_GROUPS: Dict[str, tuple[str, ...]] = {
    "hard_constraints": (
        "vibe_match",
        "budget_diff_ratio",
        "bookings_preserved_ratio",
        "must_see_preserved_ratio",
    ),
    "temporal": (
        "time_shift_minutes",
        "activity_count_change",
    ),
    "spatial": (
        "location_distance_km",
    ),
    "magnitude": (
        "num_activities_changed",
        "ratio_activities_changed",
    ),
    "context": (
        "anchor_age_minutes",
        "num_turns_since_anchor",
        "num_prior_replans",
    ),
    "explicit_user": (
        "user_explicitly_changed_vibe",
        "user_explicitly_changed_budget",
    ),
}


def features_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return the 14 model features as a name-keyed mapping."""
    return {name: row.get(name, 0.0) for name in FEATURE_NAMES}


def rules_broken(features: Dict[str, Any]) -> bool:
    """Apply the 7 ground-truth intent rules; True when intent is broken.

    Mirrors :meth:`IntentLabeler.label` so the rule arm is a faithful
    rules-only baseline.
    """
    if float(features.get("bookings_preserved_ratio", 1.0)) < 1.0 - 1e-9:
        return True
    if float(features.get("must_see_preserved_ratio", 1.0)) < 1.0 - 1e-9:
        return True
    if (
        int(features.get("vibe_match", 1)) == 0
        and int(features.get("user_explicitly_changed_vibe", 0)) == 0
    ):
        return True
    if (
        float(features.get("budget_diff_ratio", 0.0)) > BUDGET_OVERRUN_THRESHOLD
        and int(features.get("user_explicitly_changed_budget", 0)) == 0
    ):
        return True
    if (
        float(features.get("time_shift_minutes", 0.0))
        > TIME_SHIFT_THRESHOLD_MINUTES + 1e-9
    ):
        return True
    if (
        float(features.get("location_distance_km", 0.0))
        > LOCATION_SHIFT_THRESHOLD_KM + 1e-9
    ):
        return True
    if (
        int(features.get("num_activities_changed", 0)) >= MIN_MINOR_CHANGES
        and int(features.get("user_explicitly_changed_vibe", 0)) == 0
        and int(features.get("user_explicitly_changed_budget", 0)) == 0
    ):
        return True
    return False


def run_rules(row: Dict[str, Any]) -> Dict[str, Any]:
    """Run the rules-only baseline on a single dataset row."""
    features = features_from_row(row)
    broken = rules_broken(features)
    return {
        "pred_label": 1 if broken else 0,
        "prob": 1.0 if broken else 0.0,
        "pred_broken": broken,
        "decision": DECISION_BROKEN if broken else DECISION_PRESERVED,
    }


def run_ml(row: Dict[str, Any], classifier: Any) -> Dict[str, Any]:
    """Run the ML classifier on a single dataset row."""
    features = features_from_row(row)
    prediction = classifier.predict(features)
    p_preserved = float(prediction["probability"])
    broken = not bool(prediction["intent_preserved"])
    return {
        "pred_label": 1 if broken else 0,
        "prob": 1.0 - p_preserved,
        "p_preserved": p_preserved,
        "pred_broken": broken,
        "decision": DECISION_BROKEN if broken else DECISION_PRESERVED,
    }


def run_hybrid(row: Dict[str, Any], classifier: Any) -> Dict[str, Any]:
    """Run the hybrid (rules + ML) pipeline on a single dataset row."""
    features = features_from_row(row)
    rule_broken = rules_broken(features)

    prediction = classifier.predict(features)
    ml_block = {
        "probability": float(prediction["probability"]),
        "preserved": bool(prediction["intent_preserved"]),
        "model_used": prediction.get("model_used", "random_forest"),
    }
    fused = fuse_intent_decision(
        not rule_broken,
        ml_block,
        confirm_threshold=DEFAULT_CONFIRM_THRESHOLD,
        no_preserve_threshold=DEFAULT_NO_PRESERVE_THRESHOLD,
    )

    broken = fused["decision"] == DECISION_BROKEN
    return {
        "pred_label": 1 if broken else 0,
        "prob": 1.0 - float(prediction["probability"]),
        "decision": fused["decision"],
        "requires_confirmation": fused["requires_confirmation"],
        "detected_by": fused["detected_by"],
        "rule_broken": rule_broken,
    }


def make_record(
    row: Dict[str, Any], prediction: Dict[str, Any]
) -> PredictionRecord:
    """Merge a prediction with the ground truth into a single record."""
    record: PredictionRecord = {
        "true_label": true_label(row),
        "pred_label": int(prediction["pred_label"]),
        "prob": float(prediction["prob"]),
        "intended_broken_type": str(
            row.get("intended_broken_type", "preserved")
        ),
    }
    for key in (
        "p_preserved",
        "pred_broken",
        "rule_broken",
        "decision",
        "requires_confirmation",
        "detected_by",
    ):
        if key in prediction:
            record[key] = prediction[key]
    return record


def true_label(row: Dict[str, Any]) -> int:
    """Return the binary ground-truth label (1 = broken / not preserved)."""
    return 1 if int(row.get("label", LABEL_BROKEN)) == LABEL_BROKEN else 0


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
            "positive_broken": int(y_true.sum()),
            "negative_preserved": int((y_true == 0).sum()),
        },
    }

    if len(set(y_true.tolist())) > 1:
        metrics["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 4)
    else:
        metrics["roc_auc"] = None
        LOGGER.warning("ROC-AUC undefined: only one class present")

    return metrics


def broken_type_metrics(
    records: Sequence[PredictionRecord],
) -> Dict[str, Any]:
    """Compute detection rate per construction break type.

    Rows labelled ``preserved`` are excluded. ``recall`` here is how often
    the variant flags a row built with that break type as broken.
    """
    per_type: Dict[str, Dict[str, Any]] = {}
    for break_type in BROKEN_TYPES:
        subset = [
            record
            for record in records
            if record["true_label"] == 1
            and record.get("intended_broken_type") == break_type
        ]
        if not subset:
            continue
        detected = sum(1 for record in subset if record["pred_label"] == 1)
        per_type[break_type] = {
            "support": len(subset),
            "detected": int(detected),
            "recall": round(detected / len(subset), 4),
        }
    return per_type


def build_result(
    variant: str,
    records: Sequence[PredictionRecord],
    **extra: Any,
) -> Dict[str, Any]:
    """Bundle presence + per-break-type metrics for a variant."""
    payload: Dict[str, Any] = {
        "variant": variant,
        "n_samples": len(records),
        "presence": presence_metrics(records),
        "per_broken_type": broken_type_metrics(records),
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
    lines = [
        f"Variant: {payload.get('variant', '?')}",
        f"  Samples         : {payload.get('n_samples', '?')}",
        "  Presence (positive = broken):",
        f"    accuracy      : {presence.get('accuracy')}",
        f"    precision     : {presence.get('precision')}",
        f"    recall        : {presence.get('recall')}",
        f"    f1            : {presence.get('f1')}",
        f"    roc_auc       : {presence.get('roc_auc')}",
        f"    confusion     : {presence.get('confusion_matrix')}",
        "  Per broken type (recall):",
    ]
    for break_type, entry in (payload.get("per_broken_type") or {}).items():
        lines.append(
            f"    {break_type:<18}: {entry['recall']} "
            f"({entry['detected']}/{entry['support']})"
        )
    return "\n".join(lines)


__all__ = [
    "PredictionRecord",
    "FEATURE_GROUPS",
    "true_label",
    "features_from_row",
    "rules_broken",
    "run_rules",
    "run_ml",
    "run_hybrid",
    "make_record",
    "presence_metrics",
    "broken_type_metrics",
    "curve_data",
    "build_result",
    "save_result",
    "summary_table",
    "DECISION_PRESERVED",
    "DECISION_BROKEN",
    "DECISION_UNCERTAIN",
]
