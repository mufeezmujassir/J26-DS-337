"""Tests for the Wandaraya Dynamic Replanning module.

Run with:  pytest wandaraya-backend/scripts/test_dynamic_replanning.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.replanning.dynamic_replanning.alternative_finder import (  # noqa: E402
    AlternativeFinder,
)
from app.replanning.dynamic_replanning.confirmation_flow import (  # noqa: E402
    ConfirmationFlow,
)
from app.replanning.dynamic_replanning.cross_turn_consistency import (  # noqa: E402
    CrossTurnConsistency,
)
from app.replanning.dynamic_replanning.intent_preserver import (  # noqa: E402
    IntentPreserver,
)
from app.replanning.dynamic_replanning.multi_turn_tracker import (  # noqa: E402
    MultiTurnTracker,
)
from app.replanning.dynamic_replanning.replanner import (  # noqa: E402
    DynamicReplanner,
)
from app.replanning.dynamic_replanning.state_manager import (  # noqa: E402
    ReplanningStateManager,
)
from app.schemas.replanning import (  # noqa: E402
    AffectedElement,
    ConfirmationResult,
    ConsistencyCheck,
    IntentAnchor,
    RevisedActivity,
    RevisedPlan,
    TurnRecord,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def original_itinerary() -> dict:
    return {
        "plan_id": "orig_plan_001",
        "vibe": "relaxed",
        "budget_total": 1200.0,
        "confirmed_bookings": ["hotel_001", "guide_002"],
        "must_see": ["Sigiriya"],
    }


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


@pytest.fixture
def memory_state() -> ReplanningStateManager:
    """State manager forced to memory-only (no Redis, no Postgres)."""
    return ReplanningStateManager(backend="memory", enable_postgres=False)


# ---------------------------------------------------------------------------
# 1. IntentPreserver
# ---------------------------------------------------------------------------


class TestIntentPreserver:
    def test_preserve_all_ok(
        self, anchor, original_itinerary, revised_plan
    ) -> None:
        preserver = IntentPreserver()
        report = preserver.preserve(
            original_itinerary, revised_plan, anchor
        )
        assert report["is_preserved"] is True
        assert set(report["preserved_elements"]) >= {
            "vibe",
            "budget",
            "bookings",
        }
        assert report["broken_elements"] == []

    def test_budget_broken(
        self, anchor, revised_plan
    ) -> None:
        preserver = IntentPreserver()
        bad_itinerary = {
            "budget_total": 2000.0,  # exceeds anchor.budget (1500)
            "confirmed_bookings": ["hotel_001", "guide_002"],
        }
        report = preserver.preserve(bad_itinerary, revised_plan, anchor)
        assert report["is_preserved"] is False
        assert "budget" in report["broken_elements"]
        assert "restore" in report["recommendation"].lower()

    def test_bookings_broken(
        self, anchor, revised_plan
    ) -> None:
        preserver = IntentPreserver()
        bad_itinerary = {
            "budget_total": 1000.0,
            "confirmed_bookings": ["hotel_999"],  # not in anchor
        }
        report = preserver.preserve(bad_itinerary, revised_plan, anchor)
        assert report["is_preserved"] is False
        assert "bookings" in report["broken_elements"]

    def test_non_strict_vibe(
        self, anchor, original_itinerary, revised_plan
    ) -> None:
        preserver = IntentPreserver(strict_vibe=False)
        assert preserver.is_vibe_preserved(
            original_itinerary, revised_plan, anchor
        ) is True

    def test_non_numeric_budget_does_not_crash(
        self, anchor, revised_plan
    ) -> None:
        preserver = IntentPreserver()
        weird = {"budget_total": "abc"}
        report = preserver.preserve(weird, revised_plan, anchor)
        assert report["is_preserved"] is True

    def test_get_preserved_elements(
        self, anchor, original_itinerary, revised_plan
    ) -> None:
        preserver = IntentPreserver()
        elements = preserver.get_preserved_elements(
            original_itinerary, revised_plan, anchor
        )
        assert isinstance(elements, list)
        assert "must_see" in elements


# ---------------------------------------------------------------------------
# 2. AlternativeFinder (with mocked Component 1)
# ---------------------------------------------------------------------------


class TestAlternativeFinder:
    def test_step_level_mocked(
        self, anchor
    ) -> None:
        fake_c1 = MagicMock(
            return_value={
                "alternatives": [
                    {"activity_name": "Museum", "time_slot": "morning"},
                    {"activity_name": "Park", "time_slot": "morning"},
                ]
            }
        )
        finder = AlternativeFinder(call_c1=fake_c1)
        affected = AffectedElement(
            activity_name="Temple",
            day="Day 1",
            time_slot="morning",
            location="Kandy",
        )
        alts = finder.find_for_step_level(affected, anchor)
        assert len(alts) == 2
        assert alts[0]["activity_name"] == "Museum"
        fake_c1.assert_called_once()

    def test_day_level_mocked(self, anchor) -> None:
        fake_c1 = MagicMock(
            return_value={"results": [{"name": "Full-day cultural tour"}]}
        )
        finder = AlternativeFinder(call_c1=fake_c1)
        alts = finder.find_for_day_level("Day 2", anchor)
        assert len(alts) == 1

    def test_plan_level_calls_both_components(
        self, anchor
    ) -> None:
        fake_c1 = MagicMock(
            return_value={"alternatives": [{"activity_name": "X"}]}
        )
        fake_c2 = MagicMock(return_value={"transport": "updated"})
        finder = AlternativeFinder(call_c1=fake_c1, call_c2=fake_c2)
        alts = finder.find_for_plan_level(
            {"disruption_id": "d1"}, anchor
        )
        assert len(alts) == 1
        fake_c2.assert_called_once()

    def test_component1_failure_returns_empty(self, anchor) -> None:
        fake_c1 = MagicMock(return_value={})  # simulates failure
        finder = AlternativeFinder(call_c1=fake_c1)
        alts = finder.find_for_step_level(
            AffectedElement(activity_name="X"), anchor
        )
        assert alts == []

    def test_component2_failure_does_not_break_plan_level(
        self, anchor
    ) -> None:
        fake_c1 = MagicMock(
            return_value={"alternatives": [{"activity_name": "X"}]}
        )
        fake_c2 = MagicMock(side_effect=Exception("boom"))
        finder = AlternativeFinder(call_c1=fake_c1, call_c2=fake_c2)
        alts = finder.find_for_plan_level({"disruption_id": "d1"}, anchor)
        assert len(alts) == 1  # C1 result survives C2 failure


# ---------------------------------------------------------------------------
# 3. MultiTurnTracker
# ---------------------------------------------------------------------------


class TestMultiTurnTracker:
    def test_track_five_turns(self, memory_state) -> None:
        tracker = MultiTurnTracker(state_manager=memory_state)
        for i in range(5):
            turn = tracker.track_turn(
                user_id="u1",
                user_message=f"msg {i}",
                system_response=f"resp {i}",
                decision="modified",
            )
            assert turn.turn_number == i + 1

        all_turns = tracker.get_all_turns("u1")
        assert len(all_turns) == 5

    def test_get_recent_turns(self, memory_state) -> None:
        tracker = MultiTurnTracker(state_manager=memory_state)
        for i in range(6):
            tracker.track_turn("u1", f"m{i}", f"r{i}", "modified")

        recent = tracker.get_recent_turns("u1", n=3)
        assert len(recent) == 3
        assert recent[-1].turn_number == 6

    def test_preference_history(self, memory_state) -> None:
        tracker = MultiTurnTracker(state_manager=memory_state)
        tracker.track_turn("u1", "a", "b", "accepted")
        tracker.track_turn("u1", "a", "b", "rejected")
        tracker.track_turn("u1", "a", "b", "rejected")

        history = tracker.get_preference_history("u1")
        assert history["decision_counts"]["accepted"] == 1
        assert history["decision_counts"]["rejected"] == 2
        assert history["decision_counts"]["total"] == 3

    def test_invalid_decision_defaults_to_modified(
        self, memory_state
    ) -> None:
        tracker = MultiTurnTracker(state_manager=memory_state)
        turn = tracker.track_turn("u1", "a", "b", "nonsense")
        assert turn.decision == "modified"


# ---------------------------------------------------------------------------
# 4. CrossTurnConsistency
# ---------------------------------------------------------------------------


class TestCrossTurnConsistency:
    def test_consistent_plan(self, anchor, revised_plan) -> None:
        checker = CrossTurnConsistency()
        result = checker.check_consistency("u1", revised_plan, anchor)
        assert isinstance(result, ConsistencyCheck)
        assert result.consistent is True
        assert result.reasons == []

    def test_explain_consistent(self, anchor, revised_plan) -> None:
        checker = CrossTurnConsistency()
        check = checker.check_consistency("u1", revised_plan, anchor)
        explanation = checker.explain_inconsistency(check)
        assert "consistent" in explanation.lower()

    def test_explain_inconsistent(self) -> None:
        checker = CrossTurnConsistency()
        check = ConsistencyCheck(
            consistent=False, reasons=["vibe drift detected"]
        )
        explanation = checker.explain_inconsistency(check)
        assert "vibe drift" in explanation

    def test_detect_intent_drift_on_reject(self, anchor) -> None:
        checker = CrossTurnConsistency()
        turn = TurnRecord(
            turn_number=1,
            user_message="no",
            system_response="ok",
            decision="rejected",
        )
        assert checker.detect_intent_drift("u1", turn, anchor) is True

    def test_no_drift_on_accept(self, anchor) -> None:
        checker = CrossTurnConsistency()
        turn = TurnRecord(
            turn_number=1,
            user_message="yes",
            system_response="ok",
            decision="accepted",
        )
        assert checker.detect_intent_drift("u1", turn, anchor) is False


# ---------------------------------------------------------------------------
# 5. ConfirmationFlow
# ---------------------------------------------------------------------------


class TestConfirmationFlow:
    def test_present_returns_required_fields(
        self, memory_state, revised_plan
    ) -> None:
        flow = ConfirmationFlow(state_manager=memory_state)
        payload = flow.present(
            "u1",
            revised_plan,
            {"preserved_elements": ["vibe", "budget"]},
        )
        assert "disruption_summary" in payload
        assert "revised_plan_summary" in payload
        assert payload["preserved_elements"] == ["vibe", "budget"]
        assert payload["requires_confirmation"] is True

    def test_default_confirmation_is_rejected(
        self, memory_state, revised_plan
    ) -> None:
        flow = ConfirmationFlow(state_manager=memory_state)
        flow.present("u1", revised_plan, {})
        result = flow.get_user_confirmation("u1")
        assert isinstance(result, ConfirmationResult)
        assert result.accepted is False
        assert result.next_action == "find_alternative"

    def test_apply_plan_records_acceptance(
        self, memory_state, revised_plan
    ) -> None:
        flow = ConfirmationFlow(state_manager=memory_state)
        flow.apply_plan("u1", revised_plan)
        result = flow.get_user_confirmation("u1")
        assert result.accepted is True
        assert result.next_action == "apply"

    def test_request_alternative(self, memory_state) -> None:
        flow = ConfirmationFlow(state_manager=memory_state)
        flow.request_alternative("u1")
        result = flow.get_user_confirmation("u1")
        assert result.accepted is False
        assert result.next_action == "find_alternative"


# ---------------------------------------------------------------------------
# 6. State Manager (memory backend)
# ---------------------------------------------------------------------------


class TestStateManager:
    def test_anchor_roundtrip(self, memory_state, anchor) -> None:
        memory_state.set_intent_anchor("u1", anchor)
        loaded = memory_state.get_intent_anchor("u1")
        assert loaded is not None
        assert loaded.vibe == anchor.vibe
        assert loaded.budget == anchor.budget

    def test_plan_roundtrip(
        self, memory_state, revised_plan
    ) -> None:
        memory_state.update_current_plan("u1", revised_plan)
        loaded = memory_state.get_current_plan("u1")
        assert loaded is not None
        assert loaded.plan_id == revised_plan.plan_id

    def test_turns_append(
        self, memory_state, anchor
    ) -> None:
        for i in range(3):
            memory_state.add_turn(
                "u1",
                TurnRecord(
                    turn_number=i + 1,
                    user_message=f"m{i}",
                    system_response=f"r{i}",
                    decision="modified",
                ),
            )
        context = memory_state.get_conversation_context("u1")
        assert len(context) == 3

    def test_clear_state(self, memory_state, anchor) -> None:
        memory_state.set_intent_anchor("u1", anchor)
        memory_state.clear_state("u1")
        assert memory_state.get_intent_anchor("u1") is None

    def test_stats_reports_memory_backend(
        self, memory_state
    ) -> None:
        stats = memory_state.get_stats()
        assert stats["active_backend"] == "memory"
        assert stats["redis_connected"] is False


# ---------------------------------------------------------------------------
# 7. DynamicReplanner end-to-end
# ---------------------------------------------------------------------------


class TestDynamicReplannerEndToEnd:
    def test_replan_step_level(self) -> None:
        replanner = DynamicReplanner()
        # Force memory state
        replanner._state_manager = ReplanningStateManager(
            backend="memory", enable_postgres=False
        )
        replanner._confirmation_flow = ConfirmationFlow(
            state_manager=replanner._state_manager
        )

        # Mock alternative finder so no HTTP goes out
        replanner._alternative_finder = AlternativeFinder(
            call_c1=lambda payload: {
                "alternatives": [
                    {"activity_name": "Alt A", "time_slot": "morning"}
                ]
            },
            call_c2=lambda payload: {},
        )

        disruption = {
            "disruption_id": "d_001",
            "severity": "step",
            "affected_element": {
                "activity_name": "Temple",
                "day": "Day 1",
                "time_slot": "morning",
                "location": "Kandy",
            },
        }
        original = {
            "plan_id": "orig_001",
            "vibe": "relaxed",
            "budget_total": 1000.0,
            "confirmed_bookings": ["hotel_001"],
            "must_see": ["Sigiriya"],
        }

        revised = replanner.replan(disruption, "u_e2e", original)

        assert isinstance(revised, RevisedPlan)
        assert revised.severity == "step"
        assert revised.disruption_id == "d_001"
        assert len(revised.revised_activities) == 1
        assert revised.requires_confirmation is True

    def test_replan_day_level(self) -> None:
        replanner = DynamicReplanner()
        replanner._state_manager = ReplanningStateManager(
            backend="memory", enable_postgres=False
        )
        replanner._confirmation_flow = ConfirmationFlow(
            state_manager=replanner._state_manager
        )
        replanner._alternative_finder = AlternativeFinder(
            call_c1=lambda payload: {
                "alternatives": [
                    {"activity_name": "Indoor tour", "time_slot": "all-day"}
                ]
            }
        )

        disruption = {
            "disruption_id": "d_002",
            "severity": "day",
            "affected_element": {"activity_name": "Beach", "day": "Day 2"},
        }
        revised = replanner.replan(disruption, "u_e2e_day", {
            "plan_id": "orig_002",
            "vibe": "relaxed",
            "budget_total": 1000.0,
        })
        assert revised.severity == "day"

    def test_replan_plan_level_calls_c2(self) -> None:
        c2_mock = MagicMock(return_value={"transport": "ok"})
        replanner = DynamicReplanner()
        replanner._state_manager = ReplanningStateManager(
            backend="memory", enable_postgres=False
        )
        replanner._confirmation_flow = ConfirmationFlow(
            state_manager=replanner._state_manager
        )
        replanner._alternative_finder = AlternativeFinder(
            call_c1=lambda payload: {
                "alternatives": [{"activity_name": "X"}]
            },
            call_c2=c2_mock,
        )

        disruption = {
            "disruption_id": "d_003",
            "severity": "plan",
            "affected_element": {"activity_name": "Route A"},
        }
        revised = replanner.replan(disruption, "u_e2e_plan", {
            "plan_id": "orig_003",
            "vibe": "active",
            "budget_total": 2000.0,
        })
        assert revised.severity == "plan"
        c2_mock.assert_called_once()

    def test_confirm_and_apply(self) -> None:
        replanner = DynamicReplanner()
        replanner._state_manager = ReplanningStateManager(
            backend="memory", enable_postgres=False
        )
        replanner._confirmation_flow = ConfirmationFlow(
            state_manager=replanner._state_manager
        )
        plan = RevisedPlan(
            severity="step",
            affected_element=AffectedElement(activity_name="X"),
        )
        replanner.apply("u1", plan)
        result = replanner.confirm("u1", plan)
        assert result.accepted is True

    def test_replan_invalid_severity_defaults_to_step(self) -> None:
        replanner = DynamicReplanner()
        replanner._state_manager = ReplanningStateManager(
            backend="memory", enable_postgres=False
        )
        replanner._confirmation_flow = ConfirmationFlow(
            state_manager=replanner._state_manager
        )
        replanner._alternative_finder = AlternativeFinder(
            call_c1=lambda payload: {"alternatives": []}
        )

        disruption = {
            "disruption_id": "d_bad",
            "severity": "nonsense",
            "affected_element": {"activity_name": "X"},
        }
        revised = replanner.replan(disruption, "u_bad", {
            "plan_id": "orig",
            "vibe": "relaxed",
            "budget_total": 500.0,
        })
        assert revised.severity == "step"


# ---------------------------------------------------------------------------
# 8. Utils sanity
# ---------------------------------------------------------------------------


class TestUtils:
    def test_load_config_defaults(self) -> None:
        from app.replanning.dynamic_replanning.utils import load_config
        config = load_config()
        assert "intent_preservation" in config
        assert "replanning" in config
        assert "component1" in config

    def test_generate_id_unique(self) -> None:
        from app.replanning.dynamic_replanning.utils import generate_id
        a = generate_id("plan")
        b = generate_id("plan")
        assert a != b
        assert a.startswith("plan_")

    def test_now_utc_is_aware(self) -> None:
        from app.replanning.dynamic_replanning.utils import now_utc
        dt = now_utc()
        assert dt.tzinfo is not None

    def test_call_component1_api_no_url(self) -> None:
        """When COMPONENT1_API_URL is unset, returns {}."""
        from app.replanning.dynamic_replanning.utils import (
            call_component1_api,
        )
        with patch.dict("os.environ", {"COMPONENT1_API_URL": ""}, clear=False):
            assert call_component1_api({"x": 1}) == {}

    def test_call_component1_api_http_error(self) -> None:
        """A network error returns {} instead of raising."""
        from app.replanning.dynamic_replanning.utils import (
            call_component1_api,
        )
        with patch.dict(
            "os.environ",
            {"COMPONENT1_API_URL": "http://127.0.0.1:1/nope"},
            clear=False,
        ), patch(
            "app.replanning.dynamic_replanning.utils.requests.post",
            side_effect=Exception("boom"),
        ):
            # The helper catches RequestException, not generic Exception;
            # use requests.RequestException to test correctly
            import requests
            with patch(
                "app.replanning.dynamic_replanning.utils.requests.post",
                side_effect=requests.ConnectionError("boom"),
            ):
                assert call_component1_api({"x": 1}) == {}