"""Tests for the intent-preservation dataset, classifier, and evaluators."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.replanning.dynamic_replanning.classifiers import (  # noqa: E402
    BROKEN_BUDGET_OVERRUN,
    BROKEN_LOCATION_SHIFT,
    BROKEN_MISSING_BOOKING,
    BROKEN_MISSING_MUST_SEE,
    BROKEN_MULTIPLE_MINOR,
    BROKEN_TIME_SHIFT,
    BROKEN_TYPES,
    BROKEN_VIBE_MISMATCH,
    DURATION_VALUES,
    FEATURE_NAMES,
    LABEL_BROKEN,
    LABEL_PRESERVED,
    MODEL_FILENAME,
    PERSONAS,
    RAW_ATTRACTIONS_FILENAME,
    RAW_DIR,
)
from app.replanning.dynamic_replanning.classifiers._dataset_io import (  # noqa: E402
    compute_sha256,
    load_jsonl,
    save_jsonl,
    stratified_split,
    write_metadata,
)
from app.replanning.dynamic_replanning.classifiers._disruption_simulator import (  # noqa: E402
    DisruptionSimulator,
)
from app.replanning.dynamic_replanning.classifiers._evaluation import (  # noqa: E402
    FEATURE_GROUPS,
    broken_type_metrics,
    features_from_row,
    make_record,
    presence_metrics,
    rules_broken,
    run_hybrid,
    run_ml,
    run_rules,
)
from app.replanning.dynamic_replanning.classifiers._feature_extractor import (  # noqa: E402
    extract_features,
)
from app.replanning.dynamic_replanning.classifiers._itinerary_generator import (  # noqa: E402
    ItineraryGenerator,
)
from app.replanning.dynamic_replanning.classifiers._labeler import (  # noqa: E402
    IntentLabeler,
)
from app.replanning.dynamic_replanning.classifiers.build_intent_dataset import (  # noqa: E402
    build_break_plan,
)
from app.replanning.dynamic_replanning.intent_classifier import (  # noqa: E402
    IntentClassifier,
)
from app.replanning.dynamic_replanning.intent_preserver import (  # noqa: E402
    DECISION_BROKEN,
    DECISION_PRESERVED,
    DECISION_UNCERTAIN,
    IntentPreserver,
    fuse_intent_decision,
)
from app.schemas.replanning import (  # noqa: E402
    AffectedElement,
    IntentAnchor,
    RevisedActivity,
    RevisedPlan,
)

RAW_ATTRACTIONS_PATH = RAW_DIR / RAW_ATTRACTIONS_FILENAME



# Fixtures


@pytest.fixture(scope="session")
def generator() -> ItineraryGenerator:
    return ItineraryGenerator(RAW_ATTRACTIONS_PATH, seed=42)


@pytest.fixture(scope="session")
def simulator(generator: ItineraryGenerator) -> DisruptionSimulator:
    return DisruptionSimulator(seed=42, attractions=generator.attractions)


@pytest.fixture(scope="session")
def sample_itinerary(generator: ItineraryGenerator) -> Dict[str, Any]:
    return generator.generate_batch(1)[0]


@pytest.fixture(scope="session")
def labeled_rows(
    generator: ItineraryGenerator, simulator: DisruptionSimulator
) -> List[Dict[str, Any]]:
    """A small deterministic feature/labeled dataset for classifier tests."""
    labeler = IntentLabeler(seed=42)
    rows: List[Dict[str, Any]] = []
    break_cycle = [None] + list(BROKEN_TYPES)
    itineraries = generator.generate_batch(160)
    for index, itinerary in enumerate(itineraries):
        disruption = simulator.simulate_disruption(itinerary)
        break_type = break_cycle[index % len(break_cycle)]
        revised = simulator.apply_disruption(
            itinerary, disruption, break_type=break_type
        )
        features = extract_features(itinerary, disruption, revised)
        label = labeler.label(itinerary, disruption, revised, features)
        rows.append(
            {
                **features,
                "label": label,
                "intended_broken_type": break_type or "preserved",
            }
        )
    return rows


@pytest.fixture(scope="session")
def trained_classifier(
    labeled_rows: List[Dict[str, Any]],
    tmp_path_factory: pytest.TempPathFactory,
) -> IntentClassifier:
    """Train a tiny Random Forest into a temp dir and load it."""
    import joblib
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier

    features = np.asarray(
        [[float(row[name]) for name in FEATURE_NAMES] for row in labeled_rows],
        dtype=float,
    )
    labels = np.asarray(
        [1 if row["label"] == LABEL_PRESERVED else 0 for row in labeled_rows],
        dtype=int,
    )

    model = RandomForestClassifier(
        n_estimators=10, class_weight="balanced", random_state=42
    ).fit(features, labels)

    model_dir = tmp_path_factory.mktemp("intent_models")
    joblib.dump(model, model_dir / MODEL_FILENAME)

    classifier = IntentClassifier(model_dir)
    classifier.load_model()
    return classifier


# Itinerary generator


def test_generator_is_deterministic() -> None:
    first = ItineraryGenerator(RAW_ATTRACTIONS_PATH, seed=7).generate_batch(5)
    second = ItineraryGenerator(RAW_ATTRACTIONS_PATH, seed=7).generate_batch(5)
    assert first == second


def test_itinerary_duration_and_persona_domains(
    generator: ItineraryGenerator,
) -> None:
    for itinerary in generator.generate_batch(30):
        assert itinerary["duration_days"] in DURATION_VALUES
        assert itinerary["persona"] in PERSONAS
        assert itinerary["activities"]


def test_itinerary_backed_by_real_attractions(
    generator: ItineraryGenerator,
) -> None:
    real_ids = {int(a["attraction_id"]) for a in generator.attractions}
    for itinerary in generator.generate_batch(10):
        for activity in itinerary["activities"]:
            assert int(activity["attraction_id"]) in real_ids


# Disruption simulator


def test_simulate_disruption_is_deterministic(
    generator: ItineraryGenerator,
) -> None:
    itinerary = generator.generate_batch(1)[0]
    first = DisruptionSimulator(seed=11, attractions=generator.attractions)
    second = DisruptionSimulator(seed=11, attractions=generator.attractions)
    assert first.simulate_disruption(itinerary) == second.simulate_disruption(
        itinerary
    )


def test_every_break_type_labels_as_broken(
    generator: ItineraryGenerator,
    simulator: DisruptionSimulator,
) -> None:
    labeler = IntentLabeler(seed=42)
    itinerary = generator.generate_batch(1)[0]
    disruption = simulator.simulate_disruption(itinerary)
    for break_type in BROKEN_TYPES:
        revised = simulator.apply_disruption(
            itinerary, disruption, break_type=break_type
        )
        features = extract_features(itinerary, disruption, revised)
        assert (
            labeler.label(itinerary, disruption, revised, features)
            == LABEL_BROKEN
        )


def test_preserved_default_labels_as_preserved(
    sample_itinerary: Dict[str, Any],
    simulator: DisruptionSimulator,
) -> None:
    labeler = IntentLabeler(seed=42)
    disruption = simulator.simulate_disruption(sample_itinerary)
    revised = simulator.apply_disruption(
        sample_itinerary, disruption, break_type=None
    )
    features = extract_features(sample_itinerary, disruption, revised)
    assert (
        labeler.label(sample_itinerary, disruption, revised, features)
        == LABEL_PRESERVED
    )


# Feature extractor


def test_feature_extractor_returns_all_14_numeric(
    sample_itinerary: Dict[str, Any],
    simulator: DisruptionSimulator,
) -> None:
    disruption = simulator.simulate_disruption(sample_itinerary)
    revised = simulator.apply_disruption(sample_itinerary, disruption)
    features = extract_features(sample_itinerary, disruption, revised)

    assert set(features.keys()) == set(FEATURE_NAMES)
    for name in FEATURE_NAMES:
        float(features[name])


def test_feature_extractor_flags_budget_overrun() -> None:
    original = {
        "itinerary_id": "o",
        "vibe": "relaxed",
        "cost_total": 1000.0,
        "confirmed_bookings": ["b1"],
        "must_see": [],
        "activities": [],
    }
    revised = dict(original)
    revised["cost_total"] = 1200.0

    features = extract_features(original, {}, revised)
    assert features["budget_diff_ratio"] == pytest.approx(0.2)
    assert features["vibe_match"] == 1
    assert features["bookings_preserved_ratio"] == 1.0



# Labeler

def test_labeler_hard_rule_bookings() -> None:
    labeler = IntentLabeler(seed=1)
    features = {"bookings_preserved_ratio": 0.5}
    assert labeler.label({}, {}, {}, features) == LABEL_BROKEN


def test_labeler_hard_rule_budget_with_user_override() -> None:
    labeler = IntentLabeler(seed=1)
    broken = {"budget_diff_ratio": 0.5, "user_explicitly_changed_budget": 0}
    allowed = {
        "budget_diff_ratio": 0.5,
        "user_explicitly_changed_budget": 1,
    }
    assert labeler.label({}, {}, {}, broken) == LABEL_BROKEN
    assert labeler.label({}, {}, {}, allowed) == LABEL_PRESERVED


def test_label_noise_flips_expected_count() -> None:
    labeler = IntentLabeler(noise_rate=0.1, seed=3)
    labels = [LABEL_PRESERVED] * 100
    noisy = labeler.apply_label_noise(labels)
    assert sum(1 for v in noisy if v == LABEL_BROKEN) == 10


# Dataset I/O


def test_stratified_split_is_disjoint_and_covers_all(
    labeled_rows: List[Dict[str, Any]],
) -> None:
    train, dev, test = stratified_split(labeled_rows, 0.8, 0.1, 0.1, seed=42)
    assert len(train) + len(dev) + len(test) == len(labeled_rows)
    assert len(train) > len(test)


def test_jsonl_roundtrip_and_sha256(
    tmp_path: Path, labeled_rows: List[Dict[str, Any]]
) -> None:
    path = save_jsonl(labeled_rows, tmp_path / "rows.jsonl")
    assert load_jsonl(path) == labeled_rows
    digest = compute_sha256(path)
    assert len(digest) == 64


def test_write_metadata(tmp_path: Path) -> None:
    path = write_metadata({"a": 1}, tmp_path / "meta.json")
    assert path.is_file()
    assert "a" in path.read_text(encoding="utf-8")


# Dataset orchestrator plan

def test_build_break_plan_counts() -> None:
    plan = build_break_plan(3000, seed=42)
    assert len(plan) == 3000
    assert sum(1 for entry in plan if entry is None) == 2100
    from collections import Counter

    counts = Counter(entry for entry in plan if entry is not None)
    assert counts[BROKEN_VIBE_MISMATCH] == 160
    assert counts[BROKEN_BUDGET_OVERRUN] == 160
    assert counts[BROKEN_MISSING_BOOKING] == 140
    assert counts[BROKEN_MISSING_MUST_SEE] == 140
    assert counts[BROKEN_TIME_SHIFT] == 120
    assert counts[BROKEN_LOCATION_SHIFT] == 100
    assert counts[BROKEN_MULTIPLE_MINOR] == 80


# Classifier inference

def test_classifier_predict_shape(trained_classifier: IntentClassifier) -> None:
    features = {name: 0.0 for name in FEATURE_NAMES}
    result = trained_classifier.predict(features)
    assert set(result) == {"intent_preserved", "probability", "model_used"}
    assert isinstance(result["intent_preserved"], bool)
    assert 0.0 <= result["probability"] <= 1.0


def test_classifier_predict_batch_matches_single(
    trained_classifier: IntentClassifier,
    labeled_rows: List[Dict[str, Any]],
) -> None:
    sample = [features_from_row(row) for row in labeled_rows[:5]]
    batch = trained_classifier.predict_batch(sample)
    assert len(batch) == 5
    for features, prediction in zip(sample, batch):
        single = trained_classifier.predict(features)
        assert prediction["intent_preserved"] == single["intent_preserved"]


def test_classifier_non_numeric_feature_falls_back(
    trained_classifier: IntentClassifier,
) -> None:
    features = {name: "not-a-number" for name in FEATURE_NAMES}
    result = trained_classifier.predict(features)
    assert 0.0 <= result["probability"] <= 1.0


def test_missing_model_raises_clear_error(tmp_path: Path) -> None:
    classifier = IntentClassifier(tmp_path)
    with pytest.raises(FileNotFoundError) as excinfo:
        classifier.load_model()
    assert MODEL_FILENAME in str(excinfo.value)



# Hybrid fusion + preserver

@pytest.mark.parametrize(
    "rule_preserved,probability,expected_decision,expected_confirm",
    [
        (True, 0.90, DECISION_PRESERVED, False),
        (True, 0.45, DECISION_UNCERTAIN, True),
        (True, 0.20, DECISION_BROKEN, True),
        (False, 0.95, DECISION_BROKEN, True),
    ],
)
def test_fuse_intent_decision_matrix(
    rule_preserved: bool,
    probability: float,
    expected_decision: str,
    expected_confirm: bool,
) -> None:
    ml_block = {
        "probability": probability,
        "preserved": probability >= 0.5,
        "model_used": "random_forest",
    }
    result = fuse_intent_decision(rule_preserved, ml_block)
    assert result["decision"] == expected_decision
    assert result["requires_confirmation"] is expected_confirm


def test_fuse_rules_only_when_no_ml() -> None:
    assert fuse_intent_decision(True, None)["decision"] == DECISION_PRESERVED
    assert fuse_intent_decision(False, None)["decision"] == DECISION_BROKEN
    assert fuse_intent_decision(True, None)["model_used"] == "rules_only"


def test_preserver_rules_only_mode() -> None:
    anchor = IntentAnchor(
        user_id="u",
        vibe="relaxed",
        budget=1500.0,
        confirmed_bookings=["h1"],
        must_see=["Sigiriya"],
    )
    original = {
        "plan_id": "o1",
        "vibe": "relaxed",
        "budget_total": 1200.0,
        "confirmed_bookings": ["h1"],
        "must_see": ["Sigiriya"],
    }
    revised = RevisedPlan(
        original_plan_id="o1",
        disruption_id="d1",
        severity="step",
        affected_element=AffectedElement(activity_name="T"),
        preserved_elements=["vibe", "budget", "bookings"],
    )
    preserver = IntentPreserver(enable_ml=False)
    report = preserver.preserve(original, revised, anchor)
    assert report["is_preserved"] is True
    assert report["model_used"] == "rules_only"
    assert report["ml"] is None
    assert report["hybrid"]["decision"] == DECISION_PRESERVED


def test_preserver_build_features_has_all_features() -> None:
    anchor = IntentAnchor(user_id="u", vibe="relaxed", budget=1000.0)
    original = {"vibe": "relaxed", "budget_total": 900.0, "confirmed_bookings": []}
    revised = RevisedPlan(
        original_plan_id="o1",
        disruption_id="d1",
        severity="step",
        affected_element=AffectedElement(activity_name="T"),
        revised_activities=[RevisedActivity(activity_name="New")],
    )
    features = IntentPreserver.build_features(original, revised, anchor)
    assert set(features.keys()) == set(FEATURE_NAMES)


def test_preserver_hybrid_uses_ml(
    trained_classifier: IntentClassifier,
    tmp_path: Path,
) -> None:
    import joblib

    model_dir = tmp_path / "m"
    model_dir.mkdir()
    joblib.dump(
        trained_classifier.model, model_dir / MODEL_FILENAME
    )

    anchor = IntentAnchor(
        user_id="u", vibe="relaxed", budget=1500.0, confirmed_bookings=["h1"]
    )
    original = {
        "vibe": "relaxed",
        "budget_total": 1200.0,
        "confirmed_bookings": ["h1"],
    }
    revised = RevisedPlan(
        original_plan_id="o1",
        disruption_id="d1",
        severity="step",
        affected_element=AffectedElement(activity_name="T"),
        revised_activities=[RevisedActivity(activity_name="New")],
    )
    preserver = IntentPreserver(enable_ml=True, model_dir=str(model_dir))
    report = preserver.preserve(original, revised, anchor)
    assert report["model_used"] == "random_forest"
    assert report["ml"] is not None
    assert report["hybrid"]["ml_probability"] is not None



# Evaluation helpers

def test_feature_groups_cover_all_features() -> None:
    covered = {name for group in FEATURE_GROUPS.values() for name in group}
    assert covered == set(FEATURE_NAMES)


def test_rules_broken_matches_labeler(
    generator: ItineraryGenerator, simulator: DisruptionSimulator
) -> None:
    labeler = IntentLabeler(seed=42)
    itinerary = generator.generate_batch(1)[0]
    disruption = simulator.simulate_disruption(itinerary)
    for break_type in list(BROKEN_TYPES) + [None]:
        revised = simulator.apply_disruption(
            itinerary, disruption, break_type=break_type
        )
        features = extract_features(itinerary, disruption, revised)
        label = labeler.label(itinerary, disruption, revised, features)
        assert rules_broken(features) == (label == LABEL_BROKEN)


def test_run_variants_shapes(
    trained_classifier: IntentClassifier,
    labeled_rows: List[Dict[str, Any]],
) -> None:
    row = labeled_rows[0]
    for prediction in (
        run_rules(row),
        run_ml(row, trained_classifier),
        run_hybrid(row, trained_classifier),
    ):
        assert prediction["pred_label"] in (0, 1)
        assert 0.0 <= prediction["prob"] <= 1.0


def test_presence_metrics_perfect_predictions() -> None:
    records = [
        {"true_label": 1, "pred_label": 1, "prob": 0.9},
        {"true_label": 0, "pred_label": 0, "prob": 0.1},
    ]
    metrics = presence_metrics(records)
    assert metrics["accuracy"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["confusion_matrix"] == [[1, 0], [0, 1]]


def test_broken_type_metrics_recall() -> None:
    records = [
        {
            "true_label": 1,
            "pred_label": 1,
            "prob": 0.9,
            "intended_broken_type": BROKEN_VIBE_MISMATCH,
        },
        {
            "true_label": 1,
            "pred_label": 0,
            "prob": 0.4,
            "intended_broken_type": BROKEN_VIBE_MISMATCH,
        },
    ]
    metrics = broken_type_metrics(records)
    assert metrics[BROKEN_VIBE_MISMATCH]["support"] == 2
    assert metrics[BROKEN_VIBE_MISMATCH]["detected"] == 1
    assert metrics[BROKEN_VIBE_MISMATCH]["recall"] == 0.5


def test_make_record_merges_ground_truth() -> None:
    row = {"label": LABEL_BROKEN, "intended_broken_type": BROKEN_TIME_SHIFT}
    record = make_record(row, run_rules(row))
    assert record["true_label"] == 1
    assert record["intended_broken_type"] == BROKEN_TIME_SHIFT


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
