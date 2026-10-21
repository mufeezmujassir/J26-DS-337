"""Tests for the ML disruption-detection classifiers (Component 4).

Covers the real-data dataset builder, the :class:`MLClassifier` inference
wrapper, the hybrid fusion logic and an end-to-end mock-trip detection.

This file is intentionally separate from ``test_disruption_detection.py`` (the
rule-based suite) and does not modify it.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.replanning.disruption_detection.classifiers import (  # noqa: E402
    DATA_DIR,
    FEATURE_NAMES,
    LABEL_DISRUPTION,
    LABEL_NORMAL,
    RAW_DIR,
    SEVERITY_LEVELS,
    extract_features,
)
from app.replanning.disruption_detection.classifiers._dataset_io import (  # noqa: E402
    compute_sha256,
    stratified_split,
)
from app.replanning.disruption_detection.classifiers._disruption_labeler import (  # noqa: E402
    DisruptionLabeler,
)
from app.replanning.disruption_detection.classifiers._feature_sampler import (  # noqa: E402
    FeatureSampler,
)
from app.replanning.disruption_detection.classifiers.build_disruption_dataset import (  # noqa: E402
    DEFAULT_SEED,
    DEFAULT_TOTAL_ROWS,
    build_dataset,
)
from app.replanning.disruption_detection.fusion import (  # noqa: E402
    DECISION_CONFIRMED,
    DECISION_NEEDS_CONFIRMATION,
    DECISION_NONE,
    DECISION_UNCERTAIN,
    FusionEngine,
)
from app.replanning.disruption_detection.ml_classifier import (  # noqa: E402
    DISRUPTION_MODEL_FILE,
    MLClassifier,
    SCALER_FILE,
    SEVERITY_MODEL_FILE,
)

LOGGER = logging.getLogger(__name__)

DATASET_FILE = DATA_DIR / "simulated_disruptions.jsonl"
METADATA_FILE = DATA_DIR / "metadata.json"
ATTRACTIONS_FILE = RAW_DIR / "sri_lankan_attractions.jsonl"
WEATHER_FILE = RAW_DIR / "weather_monthly.jsonl"

RAW_AVAILABLE = ATTRACTIONS_FILE.is_file() and WEATHER_FILE.is_file()
requires_raw = pytest.mark.skipif(
    not RAW_AVAILABLE,
    reason="raw data sources are git-ignored and unavailable",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="session")
def dataset_rows() -> List[Dict[str, Any]]:
    """The committed frozen dataset shared across the builder tests."""
    assert DATASET_FILE.is_file(), f"missing frozen dataset: {DATASET_FILE}"
    return _load_jsonl(DATASET_FILE)


@pytest.fixture(scope="session")
def dataset_metadata() -> Dict[str, Any]:
    """The committed metadata manifest."""
    assert METADATA_FILE.is_file(), f"missing metadata: {METADATA_FILE}"
    return json.loads(METADATA_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def trained_classifier(
    tmp_path_factory: pytest.TempPathFactory,
) -> MLClassifier:
    """Train tiny models on the committed dataset and load them via MLClassifier.

    Keeps the suite fast and independent of the git-ignored model artefacts.
    """
    import joblib
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    rows = _load_jsonl(DATA_DIR / "train.jsonl")
    X = np.asarray([extract_features(row) for row in rows], dtype=float)
    y_presence = np.asarray(
        [1 if row["label"] == LABEL_DISRUPTION else 0 for row in rows], dtype=int
    )

    model_dir = tmp_path_factory.mktemp("ml_models")

    scaler = StandardScaler().fit(X)
    presence = LogisticRegression(
        class_weight="balanced", max_iter=1000, random_state=42
    ).fit(scaler.transform(X), y_presence)

    disruption_rows = [
        row for row in rows if row["label"] == LABEL_DISRUPTION
    ]
    Xd = np.asarray(
        [extract_features(row) for row in disruption_rows], dtype=float
    )
    yd = np.asarray([str(row["severity"]) for row in disruption_rows])
    severity = RandomForestClassifier(
        n_estimators=10, class_weight="balanced", random_state=42
    ).fit(Xd, yd)

    joblib.dump(presence, model_dir / DISRUPTION_MODEL_FILE)
    joblib.dump(scaler, model_dir / SCALER_FILE)
    joblib.dump(severity, model_dir / SEVERITY_MODEL_FILE)

    classifier = MLClassifier(model_dir)
    classifier.load_models()
    return classifier


# ---------------------------------------------------------------------------
# 1-5. Dataset builder
# ---------------------------------------------------------------------------

def test_dataset_produces_expected_fields(
    dataset_rows: List[Dict[str, Any]],
) -> None:
    """Every row carries the 13 features plus label/severity."""
    required = set(FEATURE_NAMES) | {"label", "severity"}
    for row in dataset_rows:
        assert required.issubset(row.keys())
        assert row["label"] in (LABEL_NORMAL, LABEL_DISRUPTION)
        assert row["severity"] in set(SEVERITY_LEVELS) | {"none"}


def test_dataset_produces_3000_rows(
    dataset_rows: List[Dict[str, Any]],
) -> None:
    """The frozen dataset always has exactly 3,000 rows."""
    assert len(dataset_rows) == 3000


def test_dataset_metadata_matches_written_files(
    dataset_rows: List[Dict[str, Any]],
    dataset_metadata: Dict[str, Any],
) -> None:
    """metadata.json distributions agree with the written dataset (80/10/10)."""
    assert dataset_metadata["num_rows"] == len(dataset_rows) == 3000
    assert dataset_metadata["train_rows"] == 2400
    assert dataset_metadata["dev_rows"] == 300
    assert dataset_metadata["test_rows"] == 300
    assert dataset_metadata["random_seed"] == DEFAULT_SEED
    assert len(dataset_metadata["dataset_hash_sha256"]) == 64

    normal = sum(1 for row in dataset_rows if row["label"] == LABEL_NORMAL)
    disruption = sum(
        1 for row in dataset_rows if row["label"] == LABEL_DISRUPTION
    )
    assert normal == dataset_metadata["label_distribution"][LABEL_NORMAL]
    assert disruption == dataset_metadata["label_distribution"][LABEL_DISRUPTION]

    for level in SEVERITY_LEVELS:
        observed = sum(
            1
            for row in dataset_rows
            if row["label"] == LABEL_DISRUPTION and row["severity"] == level
        )
        assert observed == dataset_metadata["severity_distribution"][level]


def test_stratified_split_is_deterministic(
    dataset_rows: List[Dict[str, Any]],
) -> None:
    """The 80/10/10 split is reproducible for a fixed seed."""
    first = stratified_split(dataset_rows, seed=42)
    second = stratified_split(dataset_rows, seed=42)
    assert first == second
    assert [len(split) for split in first] == [2400, 300, 300]


def test_labeler_rules() -> None:
    """The documented labelling rules produce the expected labels."""
    labeler = DisruptionLabeler()
    benign = {
        "rain_duration_hours": 1.0,
        "is_outdoor_activity": 1,
        "closure_flag": 0,
        "capacity_issue": 0,
        "crowd_level_score": 0.2,
        "heat_warning": 0,
        "complaint_score": 0.1,
        "change_request": 0,
        "gps_deviation_km": 1.0,
        "time_delay_minutes": 10,
        "num_affected_activities": 1,
        "rain_intensity_score": 0.2,
        "temperature_celsius": 25.0,
    }
    assert labeler.label(benign) == (LABEL_NORMAL, "none")

    rain = dict(benign, rain_duration_hours=4.0)
    assert labeler.label(rain) == (LABEL_DISRUPTION, "step")

    plan = dict(benign, num_affected_activities=4)
    assert labeler.label(plan) == (LABEL_DISRUPTION, "plan")


# ---------------------------------------------------------------------------
# 6-9. MLClassifier
# ---------------------------------------------------------------------------

def test_ml_classifier_loads_models(trained_classifier: MLClassifier) -> None:
    """load_models populates all three artefacts."""
    assert trained_classifier.disruption_model is not None
    assert trained_classifier.severity_model is not None
    assert trained_classifier.scaler is not None


def test_predict_disruption_shape(trained_classifier: MLClassifier) -> None:
    """predict_disruption returns a bool and a probability in [0, 1]."""
    features = {name: 0.0 for name in FEATURE_NAMES}
    features["rain_duration_hours"] = 5.0
    features["is_outdoor_activity"] = 1

    result = trained_classifier.predict_disruption(features)

    assert set(result) == {"is_disruption", "probability"}
    assert isinstance(result["is_disruption"], bool)
    assert 0.0 <= result["probability"] <= 1.0


def test_predict_severity_valid_level(trained_classifier: MLClassifier) -> None:
    """predict_severity returns one of step/day/plan with a confidence."""
    features = {name: 0.0 for name in FEATURE_NAMES}
    features["complaint_score"] = 0.9

    result = trained_classifier.predict_severity(features)

    assert result["severity"] in SEVERITY_LEVELS
    assert 0.0 <= result["confidence"] <= 1.0


def test_predict_combines_both_models(trained_classifier: MLClassifier) -> None:
    """predict returns the merged presence + severity payload."""
    features = {name: 1.0 for name in FEATURE_NAMES}
    result = trained_classifier.predict(features)

    assert set(result) >= {
        "is_disruption",
        "probability",
        "severity",
        "confidence",
        "ml_severity",
    }


# ---------------------------------------------------------------------------
# 10. Hybrid fusion logic
# ---------------------------------------------------------------------------

def _rule(name: str = "rain_3h_outdoor", severity: str = "step") -> Dict[str, Any]:
    return {
        "name": name,
        "severity": severity,
        "source": "weather",
        "category": "weather",
        "reason": {},
    }


@pytest.mark.parametrize(
    "rule_fired,probability,expected_decision,expected_disruption,expected_confirm",
    [
        (True, 0.90, DECISION_CONFIRMED, True, False),
        (True, 0.50, DECISION_NEEDS_CONFIRMATION, True, True),
        (False, 0.90, DECISION_NEEDS_CONFIRMATION, True, True),
        (False, 0.30, DECISION_NONE, False, False),
        (False, 0.50, DECISION_UNCERTAIN, False, True),
        (True, 0.20, DECISION_NEEDS_CONFIRMATION, True, True),
    ],
)
def test_fusion_decision_matrix(
    rule_fired: bool,
    probability: float,
    expected_decision: str,
    expected_disruption: bool,
    expected_confirm: bool,
) -> None:
    """Every rules + ML combination maps to the documented decision."""
    engine = FusionEngine()
    candidates = [_rule()] if rule_fired else []
    ml_prediction = {
        "is_disruption": probability >= 0.5,
        "probability": probability,
        "severity": "day",
        "ml_severity": "day",
    }

    result = engine.fuse_hybrid(candidates, ml_prediction)

    assert result["decision"] == expected_decision
    assert result["is_disruption"] is expected_disruption
    assert result["requires_confirmation"] is expected_confirm


def test_fusion_severity_takes_highest() -> None:
    """The effective severity is the strongest of rules and ML."""
    engine = FusionEngine()
    result = engine.fuse_hybrid(
        [_rule(severity="step")],
        {"is_disruption": True, "probability": 0.95, "ml_severity": "plan"},
    )
    assert result["severity"] == "plan"
    assert result["detected_by"]["ml_severity"] == "plan"


def test_fusion_detected_by_provenance() -> None:
    """detected_by lists rule names and the ML flags."""
    engine = FusionEngine()
    result = engine.fuse_hybrid(
        [_rule()],
        {"is_disruption": True, "probability": 0.8, "ml_severity": "day"},
    )
    detected_by = result["detected_by"]
    assert detected_by["rules"] == ["rain_3h_outdoor"]
    assert detected_by["ml_classifier"] is True
    assert detected_by["ml_severity"] == "day"


def test_fusion_rules_only_when_no_ml() -> None:
    """Passing no ML prediction runs the engine in rules-only mode."""
    engine = FusionEngine()
    result = engine.fuse_hybrid([_rule()], None)
    assert result["is_disruption"] is True
    assert result["decision"] == DECISION_NEEDS_CONFIRMATION


# ---------------------------------------------------------------------------
# 11. End-to-end mock trip
# ---------------------------------------------------------------------------

def _mock_trip() -> Dict[str, Any]:
    return {
        "location": {"lat": 6.9271, "lon": 79.8612},
        "place": {"name": "Sigiriya Rock Fortress", "place_id": ""},
        "itinerary": {
            "day": "Day 2",
            "activity_name": "Sigiriya climb",
            "time_slot": "09:00-11:00",
            "location": "Sigiriya",
            "scheduled_at": "09:00",
            "actual_at": "09:05",
            "is_outdoor": True,
        },
        "route_waypoints": [{"lat": 6.9271, "lon": 79.8612}],
        "chat_message": "it is raining hard and the place is crowded",
        "planner": {
            "closures_today": 0,
            "hotel_overbooked": False,
            "city_change_requested": False,
        },
    }


def test_end_to_end_mock_trip(trained_classifier: MLClassifier) -> None:
    """A mocked rainy trip is detected and can be enriched with detected_by."""
    from app.replanning.disruption_detection.detector import DisruptionDetector
    from app.replanning.disruption_detection.trigger_rules import apply_rules

    storm_signal = {
        "rain_duration_hours": 4.0,
        "rain_intensity": "storm",
        "temperature_celsius": 30.0,
        "heat_warning": False,
    }

    detector = DisruptionDetector()
    with mock.patch.object(
        detector.weather_monitor, "monitor", return_value=storm_signal
    ):
        disruptions = detector.detect_and_fuse(_mock_trip())

    assert disruptions, "expected at least one weather disruption"
    assert all(d.source == "weather" for d in disruptions)

    # Hybrid enrichment: attach the ML provenance to the rule output.
    engine = FusionEngine()
    features = {name: 0.0 for name in FEATURE_NAMES}
    features["rain_duration_hours"] = 4.0
    features["is_outdoor_activity"] = 1
    ml_prediction = trained_classifier.predict(features)

    signals = {
        "weather": storm_signal,
        "places": {},
        "gps": {},
        "complaint": {},
        "context": {"is_outdoor": True},
    }
    triggered = apply_rules(signals)
    decision = engine.fuse_hybrid(triggered, ml_prediction)

    assert decision["is_disruption"] is True
    assert decision["detected_by"]["rules"]


# ---------------------------------------------------------------------------
# 12. Missing model files
# ---------------------------------------------------------------------------

def test_missing_models_raise_clear_error(tmp_path: Path) -> None:
    """A missing model directory raises FileNotFoundError with guidance."""
    classifier = MLClassifier(tmp_path)

    with pytest.raises(FileNotFoundError) as excinfo:
        classifier.load_models()

    message = str(excinfo.value)
    assert "Missing ML model file(s)" in message
    assert DISRUPTION_MODEL_FILE in message
    assert SEVERITY_MODEL_FILE in message
    assert SCALER_FILE in message


def test_predict_before_load_raises_when_files_absent(tmp_path: Path) -> None:
    """Predicting without loadable artefacts surfaces the clear error."""
    classifier = MLClassifier(tmp_path)
    features = {name: 0.0 for name in FEATURE_NAMES}

    with pytest.raises(FileNotFoundError):
        classifier.predict_disruption(features)


# ---------------------------------------------------------------------------
# 13-19. Real-data provenance
# ---------------------------------------------------------------------------

@requires_raw
def test_real_attractions_loaded() -> None:
    """The sampler loads the real attraction source."""
    sampler = FeatureSampler(ATTRACTIONS_FILE, WEATHER_FILE, seed=42)
    sampler.load_sources()
    assert len(sampler.attractions) > 0
    assert all("district_id" in row for row in sampler.attractions)


@requires_raw
def test_real_weather_loaded() -> None:
    """The sampler loads the real weather source."""
    sampler = FeatureSampler(ATTRACTIONS_FILE, WEATHER_FILE, seed=42)
    sampler.load_sources()
    assert len(sampler.weather) > 0
    assert all("rainfall_mm" in row for row in sampler.weather)


def test_real_data_ratio_at_least_half(
    dataset_metadata: Dict[str, Any],
) -> None:
    """At least half the rows are backed by real weather data."""
    assert dataset_metadata["real_data_ratio"] >= 0.5


def test_source_attractions_count_positive(
    dataset_metadata: Dict[str, Any],
) -> None:
    """The builder records which real attractions it sampled."""
    assert dataset_metadata["source_attractions_count"] > 0


def test_dataset_hash_matches_recomputed(
    dataset_metadata: Dict[str, Any],
) -> None:
    """The committed dataset hash matches a fresh recomputation."""
    recomputed = compute_sha256(DATASET_FILE)
    assert recomputed == dataset_metadata["dataset_hash_sha256"]


@requires_raw
def test_seed42_regeneration_identical(
    tmp_path: Path,
    dataset_metadata: Dict[str, Any],
) -> None:
    """Rebuilding with the default seed reproduces the committed dataset."""
    metadata = build_dataset(
        raw_dir=RAW_DIR,
        output_dir=tmp_path,
        total_rows=DEFAULT_TOTAL_ROWS,
        seed=DEFAULT_SEED,
    )
    assert metadata["dataset_hash_sha256"] == dataset_metadata["dataset_hash_sha256"]


@requires_raw
def test_builder_produces_3000_rows(tmp_path: Path) -> None:
    """Building with the default settings yields exactly 3,000 rows."""
    metadata = build_dataset(
        raw_dir=RAW_DIR,
        output_dir=tmp_path,
        total_rows=DEFAULT_TOTAL_ROWS,
        seed=DEFAULT_SEED,
    )
    assert metadata["num_rows"] == 3000
    assert len(_load_jsonl(tmp_path / "simulated_disruptions.jsonl")) == 3000


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(pytest.main([__file__, "-v"]))
