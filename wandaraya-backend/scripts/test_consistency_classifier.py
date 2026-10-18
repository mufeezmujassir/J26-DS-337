"""Tests for the cross-turn consistency dataset, classifier, and evaluators."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.replanning.dynamic_replanning.classifiers import (  # noqa: E402
    load_jsonl,
)
from app.replanning.dynamic_replanning.classifiers._dataset_io import (  # noqa: E402
    compute_sha256,
)
from app.replanning.dynamic_replanning.classifiers.consistency import (  # noqa: E402
    CONSISTENCY_MODEL_FILENAME,
    CONSISTENCY_PROCESSED_DIR,
    CONSISTENCY_RAW_DIR,
    DRIFT_NONE,
    DRIFT_TYPES,
    FEATURE_NAMES,
    LABEL_CONSISTENT,
    LABEL_DRIFT,
    RAW_ATTRACTIONS_FILENAME,
    VIOLATION_BUDGET_EXCEEDED,
    VIOLATION_CONFIRMED_REMOVED,
    VIOLATION_MUST_SEE_REMOVED,
    VIOLATION_NO_RUSHING,
    VIOLATION_REJECTION_REINTRODUCED,
    VIOLATION_VIBE_MISMATCH,
)
from app.replanning.dynamic_replanning.classifiers.consistency._conversation_generator import (  # noqa: E402
    ConversationGenerator,
)
from app.replanning.dynamic_replanning.classifiers.consistency._drift_simulator import (  # noqa: E402
    DriftSimulator,
)
from app.replanning.dynamic_replanning.classifiers.consistency._evaluation import (  # noqa: E402
    FEATURE_GROUPS,
    drift_type_metrics,
    features_from_row,
    make_record,
    presence_metrics,
    rules_drift,
    run_hybrid,
    run_ml,
    run_rules,
    true_label,
)
from app.replanning.dynamic_replanning.classifiers.consistency._feature_extractor import (  # noqa: E402
    detect_violations,
    extract_features,
)
from app.replanning.dynamic_replanning.classifiers.consistency._labeler import (  # noqa: E402
    DriftLabeler,
)
from app.replanning.dynamic_replanning.consistency_classifier import (  # noqa: E402
    ConsistencyClassifier,
)
from app.replanning.dynamic_replanning.cross_turn_consistency import (  # noqa: E402
    CrossTurnConsistency,
)
from app.schemas.replanning import (  # noqa: E402
    AffectedElement,
    ConsistencyCheck,
    IntentAnchor,
    RevisedActivity,
    RevisedPlan,
)

RAW_PATH = CONSISTENCY_RAW_DIR / RAW_ATTRACTIONS_FILENAME
HAS_RAW = RAW_PATH.is_file()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_conversation() -> Dict[str, Any]:
    return {
        "conversation_id": "conv_test",
        "num_turns": 3,
        "constraints": {
            "vibe": "relaxed",
            "budget_usd": 500.0,
            "pace": "slow",
            "must_see": ["Sigiriya"],
            "no_rushing": True,
        },
        "confirmations": ["Polonnaruwa"],
        "rejections": ["Temple visit"],
        "initial_plan": {
            "plan_id": "plan_0",
            "vibe": "relaxed",
            "total_cost_usd": 420.0,
            "activities": [
                {"attraction_id": 1, "name": "Sigiriya", "day": 1, "start_minutes": 480},
                {"attraction_id": 2, "name": "Dambulla Cave", "day": 1, "start_minutes": 660},
            ],
        },
    }


@pytest.fixture
def clean_plan() -> Dict[str, Any]:
    return {
        "plan_id": "plan_1",
        "vibe": "relaxed",
        "total_cost_usd": 450.0,
        "activities": [
            {"attraction_id": 1, "name": "Sigiriya", "day": 1, "start_minutes": 480},
            {"attraction_id": 3, "name": "Polonnaruwa", "day": 1, "start_minutes": 660},
        ],
    }


@pytest.fixture
def anchor() -> IntentAnchor:
    return IntentAnchor(
        user_id="u_test",
        vibe="relaxed",
        budget=1500.0,
        confirmed_bookings=["hotel_001", "guide_002"],
        must_see=["Sigiriya"],
    )


@pytest.fixture
def revised_plan() -> RevisedPlan:
    return RevisedPlan(
        original_plan_id="orig_plan_001",
        disruption_id="d_001",
        severity="step",
        affected_element=AffectedElement(
            activity_name="Temple visit",
            day="Day 1",
            time_slot="morning",
            location="Kandy",
        ),
        revised_activities=[
            RevisedActivity(
                activity_name="Museum visit",
                time_slot="morning",
                duration="2h",
                reason="Step-Level replacement",
            )
        ],
        preserved_elements=["vibe", "budget", "bookings"],
        requires_confirmation=True,
    )


@pytest.fixture(scope="session")
def labeled_rows() -> List[Dict[str, Any]]:
    """A small deterministic feature/labeled dataset for classifier tests."""
    labeler = DriftLabeler(noise_rate=0.0, seed=42)
    clean = {
        "conversation_id": "conv_clean",
        "num_turns": 2,
        "constraints": {"vibe": "relaxed", "budget_usd": 300.0, "pace": "slow"},
        "confirmations": [],
        "rejections": [],
        "initial_plan": {"activities": []},
    }
    clean_plan_row = {
        "plan_id": "p0",
        "vibe": "relaxed",
        "total_cost_usd": 280.0,
        "activities": [
            {"attraction_id": 10, "name": "A", "day": 1, "start_minutes": 480},
            {"attraction_id": 11, "name": "B", "day": 1, "start_minutes": 600},
        ],
    }
    drift_plan_row = {
        "plan_id": "p1",
        "vibe": "active",
        "total_cost_usd": 900.0,
        "activities": [
            {"attraction_id": 20, "name": "C", "day": 1, "start_minutes": 480},
            {"attraction_id": 21, "name": "D", "day": 1, "start_minutes": 600},
            {"attraction_id": 22, "name": "E", "day": 1, "start_minutes": 720},
            {"attraction_id": 23, "name": "F", "day": 1, "start_minutes": 840},
        ],
    }
    rows: List[Dict[str, Any]] = []
    for variant in range(40):
        plan = clean_plan_row if variant % 2 == 0 else drift_plan_row
        conversation = dict(clean)
        conversation["conversation_id"] = f"conv_{variant % 10}"
        features = extract_features(conversation, plan)
        label = labeler.label(conversation, plan, features)
        rows.append({**features, "label": label, "intended_drift_type": "none"})
    return rows


@pytest.fixture(scope="session")
def trained_classifier(
    labeled_rows: List[Dict[str, Any]],
    tmp_path_factory: pytest.TempPathFactory,
) -> ConsistencyClassifier:
    """Train a tiny Random Forest into a temp dir and load it."""
    import joblib
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier

    features = np.asarray(
        [[float(row[name]) for name in FEATURE_NAMES] for row in labeled_rows],
        dtype=float,
    )
    labels = np.asarray([int(row["label"]) for row in labeled_rows], dtype=int)

    model = RandomForestClassifier(
        n_estimators=10, class_weight="balanced", random_state=42
    ).fit(features, labels)

    model_dir = tmp_path_factory.mktemp("consistency_models")
    joblib.dump(model, model_dir / CONSISTENCY_MODEL_FILENAME)

    classifier = ConsistencyClassifier(model_dir)
    classifier.load_model()
    return classifier


# ---------------------------------------------------------------------------
# Frozen dataset
# ---------------------------------------------------------------------------


class TestFrozenDataset:
    def test_processed_files_exist(self) -> None:
        for name in (
            "simulated_consistency_data.jsonl",
            "train.jsonl",
            "dev.jsonl",
            "test.jsonl",
            "metadata.json",
            "README.md",
        ):
            assert (CONSISTENCY_PROCESSED_DIR / name).is_file(), name

    def test_split_sizes(self) -> None:
        assert len(load_jsonl(CONSISTENCY_PROCESSED_DIR / "train.jsonl")) == 2400
        assert len(load_jsonl(CONSISTENCY_PROCESSED_DIR / "dev.jsonl")) == 300
        assert len(load_jsonl(CONSISTENCY_PROCESSED_DIR / "test.jsonl")) == 300

    def test_row_schema(self) -> None:
        rows = load_jsonl(CONSISTENCY_PROCESSED_DIR / "test.jsonl")
        for row in rows[:25]:
            for name in FEATURE_NAMES:
                assert name in row, name
            assert row["label"] in (LABEL_CONSISTENT, LABEL_DRIFT)
            assert row["intended_drift_type"] in DRIFT_TYPES + (DRIFT_NONE,)

    def test_drift_types_covered_in_train(self) -> None:
        rows = load_jsonl(CONSISTENCY_PROCESSED_DIR / "train.jsonl")
        present = {row["intended_drift_type"] for row in rows}
        for drift_type in DRIFT_TYPES:
            assert drift_type in present, drift_type

    def test_dataset_hash_matches_metadata(self) -> None:
        import json

        metadata = json.loads(
            (CONSISTENCY_PROCESSED_DIR / "metadata.json").read_text("utf-8")
        )
        digest = compute_sha256(
            CONSISTENCY_PROCESSED_DIR / "simulated_consistency_data.jsonl"
        )
        assert digest == metadata["dataset_hash_sha256"]


# ---------------------------------------------------------------------------
# Feature extractor
# ---------------------------------------------------------------------------


class TestFeatureExtractor:
    def test_extract_features_keys(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        features = extract_features(clean_conversation, clean_plan)
        assert set(features.keys()) == set(FEATURE_NAMES)

    def test_clean_pair_has_no_violations(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        assert detect_violations(clean_conversation, clean_plan) == []
        features = extract_features(clean_conversation, clean_plan)
        assert int(features["num_conflicting_constraints"]) == 0

    def test_vibe_mismatch(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        plan = dict(clean_plan, vibe="active")
        assert VIOLATION_VIBE_MISMATCH in detect_violations(clean_conversation, plan)

    def test_budget_exceeded(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        plan = dict(clean_plan, total_cost_usd=9999.0)
        assert VIOLATION_BUDGET_EXCEEDED in detect_violations(clean_conversation, plan)

    def test_must_see_removed(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        plan = dict(clean_plan)
        plan["activities"] = [plan["activities"][1]]
        assert VIOLATION_MUST_SEE_REMOVED in detect_violations(clean_conversation, plan)

    def test_confirmed_removed(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        plan = dict(clean_plan)
        plan["activities"] = [plan["activities"][0]]
        assert VIOLATION_CONFIRMED_REMOVED in detect_violations(clean_conversation, plan)

    def test_rejection_reintroduced(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        plan = dict(clean_plan)
        plan["activities"] = plan["activities"] + [
            {"attraction_id": 4, "name": "Temple visit", "day": 2, "start_minutes": 600}
        ]
        assert (
            VIOLATION_REJECTION_REINTRODUCED
            in detect_violations(clean_conversation, plan)
        )

    def test_no_rushing_violated(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        plan = dict(clean_plan)
        plan["activities"] = [
            {**clean_plan["activities"][0], "start_minutes": 480},
            {
                "attraction_id": 2,
                "name": "Dambulla Cave",
                "day": 1,
                "start_minutes": 900,
            },
            {**clean_plan["activities"][1], "start_minutes": 660},
        ]
        assert VIOLATION_NO_RUSHING in detect_violations(clean_conversation, plan)


# ---------------------------------------------------------------------------
# Labeler
# ---------------------------------------------------------------------------


class TestDriftLabeler:
    def test_labels_drift_on_violations(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        labeler = DriftLabeler(noise_rate=0.0, seed=42)
        plan = dict(clean_plan, vibe="active")
        features = extract_features(clean_conversation, plan)
        assert labeler.label(clean_conversation, plan, features) == LABEL_DRIFT

    def test_labels_consistent_when_clean(
        self, clean_conversation: Dict[str, Any], clean_plan: Dict[str, Any]
    ) -> None:
        labeler = DriftLabeler(noise_rate=0.0, seed=42)
        features = extract_features(clean_conversation, clean_plan)
        assert (
            labeler.label(clean_conversation, clean_plan, features)
            == LABEL_CONSISTENT
        )

    def test_label_noise_is_deterministic(self) -> None:
        labels = [LABEL_CONSISTENT] * 90 + [LABEL_DRIFT] * 10
        first = DriftLabeler(noise_rate=0.1, seed=42).apply_label_noise(labels)
        second = DriftLabeler(noise_rate=0.1, seed=42).apply_label_noise(labels)
        assert first == second
        assert sum(1 for a, b in zip(labels, first) if a != b) == 10


# ---------------------------------------------------------------------------
# Conversation generator + drift simulator (requires raw attractions)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_RAW, reason="raw attractions file not present")
class TestGeneratorAndSimulator:
    def test_generator_is_deterministic(self) -> None:
        first = ConversationGenerator(str(RAW_PATH), seed=7).generate_batch(3)
        second = ConversationGenerator(str(RAW_PATH), seed=7).generate_batch(3)
        assert first == second

    def test_drift_injection_flags_violation(self) -> None:
        import random

        generator = ConversationGenerator(str(RAW_PATH), seed=42)
        conversation = generator.generate_batch(1)[0]
        simulator = DriftSimulator(seed=42, generator=generator)
        result = simulator.inject_drift(
            conversation,
            drift_type=DRIFT_TYPES[0],
            rng=random.Random(3),
        )
        assert result["new_plan"] is not None

    def test_consistent_alternative_has_no_violations(self) -> None:
        generator = ConversationGenerator(str(RAW_PATH), seed=42)
        conversation = generator.generate_batch(1)[0]
        simulator = DriftSimulator(seed=42, generator=generator)
        import random

        plan = simulator.produce_consistent_alternative(
            conversation, rng=random.Random(3)
        )
        assert detect_violations(conversation, plan) == []


# ---------------------------------------------------------------------------
# ConsistencyClassifier inference
# ---------------------------------------------------------------------------


class TestConsistencyClassifier:
    def test_predict_output_contract(
        self, trained_classifier: ConsistencyClassifier
    ) -> None:
        prediction = trained_classifier.predict(
            features_from_row({"label": 0, **{name: 0.0 for name in FEATURE_NAMES}})
        )
        assert set(prediction.keys()) == {
            "drift_detected",
            "probability",
            "model_used",
        }
        assert prediction["model_used"] == "random_forest"
        assert isinstance(prediction["drift_detected"], bool)
        assert 0.0 <= prediction["probability"] <= 1.0

    def test_predict_batch_length(
        self, trained_classifier: ConsistencyClassifier
    ) -> None:
        empty_row = {name: 0.0 for name in FEATURE_NAMES}
        results = trained_classifier.predict_batch([empty_row] * 5)
        assert len(results) == 5

    def test_missing_model_raises(self, tmp_path: Path) -> None:
        classifier = ConsistencyClassifier(tmp_path)
        with pytest.raises(FileNotFoundError) as excinfo:
            classifier.load_model()
        assert CONSISTENCY_MODEL_FILENAME in str(excinfo.value)


# ---------------------------------------------------------------------------
# Hybrid CrossTurnConsistency
# ---------------------------------------------------------------------------


class TestCrossTurnConsistency:
    def test_clean_revision_passes_rules(
        self, anchor: IntentAnchor, revised_plan: RevisedPlan
    ) -> None:
        checker = CrossTurnConsistency(enable_ml=False)
        check = checker.check_consistency("u1", revised_plan, anchor)
        assert check.consistent is True
        assert check.reasons == []
        assert check.drift_probability == 0.0

    def test_must_see_replaced_is_hard_rule(
        self, anchor: IntentAnchor, revised_plan: RevisedPlan
    ) -> None:
        revised = revised_plan.model_copy()
        revised.affected_element = AffectedElement(
            activity_name="Sigiriya",
            day="Day 1",
            time_slot="morning",
            location="Sigiriya",
        )
        checker = CrossTurnConsistency(enable_ml=False)
        check = checker.check_consistency("u1", revised, anchor)
        assert check.consistent is False
        assert check.drift_probability == 1.0
        assert any("Prior constraint violated" in r for r in check.reasons)

    def test_bookings_dropped_is_hard_rule(
        self, anchor: IntentAnchor, revised_plan: RevisedPlan
    ) -> None:
        revised = revised_plan.model_copy()
        revised.preserved_elements = ["vibe"]
        checker = CrossTurnConsistency(enable_ml=False)
        check = checker.check_consistency("u1", revised, anchor)
        assert check.consistent is False
        assert check.drift_probability == 1.0
        assert any("confirmed item removed" in r for r in check.reasons)

    def test_rejection_reintroduced_is_hard_rule(
        self, anchor: IntentAnchor, revised_plan: RevisedPlan
    ) -> None:
        history = [
            {
                "constraints_stated": {"pace": "slow"},
                "rejections": ["Museum visit"],
                "confirmations": [],
            }
        ]
        checker = CrossTurnConsistency(enable_ml=False)
        check = checker.check_consistency(
            "u1", revised_plan, anchor, conversation_history=history
        )
        assert check.consistent is False
        assert any("rejected alternative" in r for r in check.reasons)

    def test_full_plan_missing_must_see(
        self, anchor: IntentAnchor
    ) -> None:
        plan = {
            "plan_id": "p_full",
            "vibe": "relaxed",
            "total_cost_usd": 900.0,
            "confirmed_bookings": ["hotel_001", "guide_002"],
            "activities": [
                {"attraction_id": 7, "name": "Museum visit", "day": 1, "start_minutes": 480}
            ],
        }
        checker = CrossTurnConsistency(enable_ml=False)
        check = checker.check_consistency("u1", plan, anchor)
        assert check.consistent is False
        assert any("Sigiriya" in r for r in check.reasons)

    def test_rf_path_used_when_rules_pass(
        self,
        anchor: IntentAnchor,
        revised_plan: RevisedPlan,
        trained_classifier: ConsistencyClassifier,
    ) -> None:
        checker = CrossTurnConsistency(enable_ml=True)
        checker._classifier = trained_classifier
        checker._classifier_checked = True
        check = checker.check_consistency("u1", revised_plan, anchor)
        assert check.reason == "RF-based consistency check"
        assert check.drift_probability is not None
        assert 0.0 <= check.drift_probability <= 1.0

    def test_hard_rules_override_ml(
        self,
        anchor: IntentAnchor,
        revised_plan: RevisedPlan,
        trained_classifier: ConsistencyClassifier,
    ) -> None:
        revised = revised_plan.model_copy()
        revised.preserved_elements = ["vibe"]
        checker = CrossTurnConsistency(enable_ml=True)
        checker._classifier = trained_classifier
        checker._classifier_checked = True
        check = checker.check_consistency("u1", revised, anchor)
        assert check.consistent is False
        assert check.drift_probability == 1.0

    def test_ml_disabled_runs_rules_only(
        self, anchor: IntentAnchor, revised_plan: RevisedPlan
    ) -> None:
        checker = CrossTurnConsistency(enable_ml=False)
        check = checker.check_consistency("u1", revised_plan, anchor)
        assert "ML unavailable" in check.reason

    def test_missing_model_degrades_gracefully(
        self, anchor: IntentAnchor, revised_plan: RevisedPlan, tmp_path: Path
    ) -> None:
        checker = CrossTurnConsistency(enable_ml=True, model_dir=str(tmp_path))
        check = checker.check_consistency("u1", revised_plan, anchor)
        assert check.consistent is True
        assert check.drift_probability == 0.0
        assert "ML unavailable" in check.reason

    def test_explain_inconsistency(self) -> None:
        checker = CrossTurnConsistency(enable_ml=False)
        consistent = ConsistencyCheck(consistent=True)
        assert "consistent" in checker.explain_inconsistency(consistent)
        inconsistent = ConsistencyCheck(
            consistent=False, reasons=["a", "b"], reason="a"
        )
        assert checker.explain_inconsistency(inconsistent) == "a"
        no_reason = ConsistencyCheck(consistent=False, reasons=["x", "y"])
        assert checker.explain_inconsistency(no_reason) == "x; y"

    def test_schema_backward_compatible(self) -> None:
        check = ConsistencyCheck(consistent=False, reasons=["vibe drift detected"])
        assert check.drift_probability is None
        assert check.reason == ""


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


class TestEvaluationHelpers:
    def test_feature_groups_cover_all_features(self) -> None:
        grouped = {name for group in FEATURE_GROUPS.values() for name in group}
        assert grouped == set(FEATURE_NAMES)

    def test_rules_drift_matches_conflicts(self) -> None:
        assert rules_drift({"num_conflicting_constraints": 2}) is True
        assert rules_drift({"num_conflicting_constraints": 0}) is False

    def test_run_rules_and_ml_and_hybrid(
        self, trained_classifier: ConsistencyClassifier
    ) -> None:
        clean_row = {name: 0.0 for name in FEATURE_NAMES}
        clean_row["label"] = LABEL_CONSISTENT
        clean_row["intended_drift_type"] = DRIFT_NONE

        rules = run_rules(clean_row)
        assert rules["pred_label"] == 0
        assert rules["prob"] == 0.0

        ml = run_ml(clean_row, trained_classifier)
        assert ml["pred_label"] in (0, 1)
        assert 0.0 <= ml["prob"] <= 1.0

        hybrid = run_hybrid(clean_row, trained_classifier)
        assert hybrid["rule_drift"] is False
        assert hybrid["detected_by"] in ("rf", "none")

    def test_run_hybrid_short_circuits_on_rules(
        self, trained_classifier: ConsistencyClassifier
    ) -> None:
        drift_row = {name: 0.0 for name in FEATURE_NAMES}
        drift_row["num_conflicting_constraints"] = 3
        drift_row["label"] = LABEL_DRIFT
        hybrid = run_hybrid(drift_row, trained_classifier)
        assert hybrid["rule_drift"] is True
        assert hybrid["prob"] == 1.0
        assert hybrid["detected_by"] == "hard_rules"

    def test_metrics_helpers(self) -> None:
        rows = [
            {
                "true_label": 0,
                "pred_label": 0,
                "prob": 0.1,
                "intended_drift_type": "none",
            },
            {
                "true_label": 1,
                "pred_label": 1,
                "prob": 0.9,
                "intended_drift_type": "budget_exceeded",
            },
            {
                "true_label": 1,
                "pred_label": 0,
                "prob": 0.2,
                "intended_drift_type": "budget_exceeded",
            },
        ]
        assert true_label({"label": LABEL_DRIFT}) == 1
        assert true_label({"label": LABEL_CONSISTENT}) == 0

        presence = presence_metrics(rows)
        assert presence["support"]["total"] == 3
        assert presence["support"]["positive_drift"] == 2

        per_type = drift_type_metrics(rows)
        assert per_type["budget_exceeded"]["support"] == 2
        assert per_type["budget_exceeded"]["detected"] == 1

        record = make_record(
            {"label": LABEL_DRIFT, "intended_drift_type": "budget_exceeded"},
            {"pred_label": 1, "prob": 0.8, "pred_drift": True},
        )
        assert record["true_label"] == 1
        assert record["prob"] == 0.8
