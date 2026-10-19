""" Rule-based Conflict Detector.

Verifies true positives and true negatives for all 5 rules, plus all specified edge cases:
- Proposal example (3 members, beach vs historical site)
- Two members wanting different destinations gives SOFT
- One member rejecting another's destination gives HARD
- Budget ranges touching at one point
- Open-ended budget handling
- Mismatched currency or scope skipped
- Synonym matching
- Self-contradiction resolution with warning
- Single member returning empty list
- Empty input returning empty list
- Bad input raising validation error
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import pytest
from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.conflict.rules import detect_conflicts
from app.group_decision.conflict.schemas import PreferenceRecord


# ---------------------------------------------------------------------------
# Rule 1: Destination HARD tests
# ---------------------------------------------------------------------------
def test_rule1_destination_hard_true_positive():
    """True Positive: One member positive, another negative about same destination."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Bob", "category": "Destination", "stance": "negative", "value": {"name": "ella"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Destination"
    assert c["severity"] == "hard"
    assert c["rule_id"] == "DEST_HARD"
    assert set(c["members"]) == {"Alice", "Bob"}
    assert c["items"]["destination"] == "ella"
    assert c["features"]["number_of_members_involved"] == 2
    assert c["features"]["number_of_supporters"] == 1
    assert c["features"]["number_of_opponents"] == 1


def test_rule1_destination_hard_true_negative():
    """True Negative: Both members positive about same destination."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
    ]
    conflicts = detect_conflicts(records)
    # Neither hard nor soft conflict because they both agree on ella
    assert len(conflicts) == 0


# ---------------------------------------------------------------------------
# Rule 2: Destination SOFT tests
# ---------------------------------------------------------------------------
def test_rule2_destination_soft_true_positive():
    """True Positive: Two members want different destinations, no member wants both."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Destination"
    assert c["severity"] == "soft"
    assert c["rule_id"] == "DEST_SOFT"
    assert set(c["members"]) == {"Alice", "Bob"}
    assert set(c["items"]["destinations"]) == {"ella", "kandy"}


def test_rule2_destination_soft_true_negative():
    """True Negative: Alice likes both Ella and Kandy; Bob likes Kandy."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
    ]
    conflicts = detect_conflicts(records)
    # Alice is positive about both ella and kandy, so no soft conflict between them
    assert len(conflicts) == 0


# ---------------------------------------------------------------------------
# Rule 3: Activity HARD tests
# ---------------------------------------------------------------------------
def test_rule3_activity_hard_true_positive():
    """True Positive: One member positive about hiking, another negative."""
    records = [
        {"member": "Alice", "category": "Activity", "stance": "positive", "value": {"name": "hiking"}},
        {"member": "Bob", "category": "Activity", "stance": "negative", "value": {"name": "hiking"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Activity"
    assert c["severity"] == "hard"
    assert c["rule_id"] == "ACTIVITY_HARD"
    assert set(c["members"]) == {"Alice", "Bob"}
    assert c["items"]["activity"] == "hiking"


def test_rule3_activity_hard_true_negative():
    """True Negative: Both members positive about hiking."""
    records = [
        {"member": "Alice", "category": "Activity", "stance": "positive", "value": {"name": "hiking"}},
        {"member": "Bob", "category": "Activity", "stance": "positive", "value": {"name": "hiking"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 0


# ---------------------------------------------------------------------------
# Rule 4: Budget tests
# ---------------------------------------------------------------------------
def test_rule4_budget_true_positive_disjoint():
    """True Positive: Budget ranges disjoint with large gap -> HARD conflict."""
    records = [
        {"member": "Alice", "category": "Budget", "stance": "positive", "value": {"min": 1000.0, "max": 3000.0, "currency": "LKR", "scope": "per_person"}},
        {"member": "Bob", "category": "Budget", "stance": "positive", "value": {"min": 6000.0, "max": 9000.0, "currency": "LKR", "scope": "per_person"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Budget"
    assert c["severity"] == "hard"
    assert c["rule_id"] == "BUDGET_DISCREPANCY"
    assert c["features"]["gap_size"] == 3000.0
    assert c["features"]["overlap_ratio"] == 0.0


def test_rule4_budget_true_negative_overlapping():
    """True Negative: Budget ranges overlap significantly (>= 30%)."""
    records = [
        {"member": "Alice", "category": "Budget", "stance": "positive", "value": {"min": 2000.0, "max": 5000.0, "currency": "LKR", "scope": "per_person"}},
        {"member": "Bob", "category": "Budget", "stance": "positive", "value": {"min": 3000.0, "max": 6000.0, "currency": "LKR", "scope": "per_person"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 0


def test_rule4_budget_touching_at_one_point():
    """Budget ranges touching at one point: overlap is 0 -> conflict."""
    records = [
        {"member": "Alice", "category": "Budget", "stance": "positive", "value": {"min": 1000.0, "max": 3000.0, "currency": "LKR", "scope": "per_person"}},
        {"member": "Bob", "category": "Budget", "stance": "positive", "value": {"min": 3000.0, "max": 5000.0, "currency": "LKR", "scope": "per_person"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Budget"
    assert c["features"]["overlap_ratio"] == 0.0
    assert c["features"]["gap_size"] == 0.0
    assert c["severity"] == "soft"  # Gap is 0, so gap_ratio is 0 <= hard_gap_ratio


def test_rule4_budget_open_ended():
    """Open-ended budget: Alice at least 8000 (max=None), Bob max 4000 (min=0)."""
    records = [
        {"member": "Alice", "category": "Budget", "stance": "positive", "value": {"min": 8000.0, "max": None, "currency": "LKR", "scope": "per_person"}},
        {"member": "Bob", "category": "Budget", "stance": "positive", "value": {"min": 0.0, "max": 4000.0, "currency": "LKR", "scope": "per_person"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "Budget"
    assert conflicts[0]["severity"] == "hard"
    assert conflicts[0]["features"]["gap_size"] == 4000.0


def test_rule4_budget_mismatched_currency_or_scope_skipped():
    """Mismatched currency or scope should be skipped without conflict."""
    # Mismatched currency: USD vs LKR
    records_curr = [
        {"member": "Alice", "category": "Budget", "stance": "positive", "value": {"min": 100.0, "max": 200.0, "currency": "USD", "scope": "per_person"}},
        {"member": "Bob", "category": "Budget", "stance": "positive", "value": {"min": 50000.0, "max": 100000.0, "currency": "LKR", "scope": "per_person"}},
    ]
    assert len(detect_conflicts(records_curr)) == 0

    # Mismatched scope: per_person vs total
    records_scope = [
        {"member": "Alice", "category": "Budget", "stance": "positive", "value": {"min": 1000.0, "max": 2000.0, "currency": "LKR", "scope": "per_person"}},
        {"member": "Bob", "category": "Budget", "stance": "positive", "value": {"min": 50000.0, "max": 80000.0, "currency": "LKR", "scope": "total"}},
    ]
    assert len(detect_conflicts(records_scope)) == 0


# ---------------------------------------------------------------------------
# Rule 5: Schedule tests
# ---------------------------------------------------------------------------
def test_rule5_schedule_date_overlap_true_positive():
    """True Positive: Date ranges do not overlap or overlap < min_overlap_days (2 days)."""
    # Overlap 1 day (only 2026-11-05), which is < 2
    records = [
        {"member": "Alice", "category": "Schedule", "stance": "positive", "value": {"start_date": "2026-11-01", "end_date": "2026-11-05"}},
        {"member": "Bob", "category": "Schedule", "stance": "positive", "value": {"start_date": "2026-11-05", "end_date": "2026-11-10"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Schedule"
    assert c["rule_id"] == "SCHEDULE_DATE_OVERLAP"
    assert c["features"]["overlap_ratio"] == 1.0  # 1 day overlap
    assert c["severity"] == "soft"


def test_rule5_schedule_date_disjoint_hard():
    """True Positive: Completely disjoint schedule dates -> HARD conflict."""
    records = [
        {"member": "Alice", "category": "Schedule", "stance": "positive", "value": {"start_date": "2026-11-01", "end_date": "2026-11-04"}},
        {"member": "Bob", "category": "Schedule", "stance": "positive", "value": {"start_date": "2026-11-10", "end_date": "2026-11-15"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Schedule"
    assert c["severity"] == "hard"
    assert c["features"]["overlap_ratio"] == 0.0
    assert c["features"]["gap_size"] == 6.0


def test_rule5_schedule_date_overlap_true_negative():
    """True Negative: Date ranges overlap by >= 2 days."""
    records = [
        {"member": "Alice", "category": "Schedule", "stance": "positive", "value": {"start_date": "2026-11-01", "end_date": "2026-11-06"}},
        {"member": "Bob", "category": "Schedule", "stance": "positive", "value": {"start_date": "2026-11-03", "end_date": "2026-11-08"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 0


def test_rule5_schedule_time_of_day_conflict():
    """True Positive: Overlapping dates but differing time_of_day preferences."""
    records = [
        {"member": "Alice", "category": "Schedule", "stance": "positive", "value": {"start_date": "2026-11-01", "end_date": "2026-11-05", "time_of_day": "morning"}},
        {"member": "Bob", "category": "Schedule", "stance": "positive", "value": {"start_date": "2026-11-01", "end_date": "2026-11-05", "time_of_day": "evening"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Schedule"
    assert c["rule_id"] == "SCHEDULE_TIME_OF_DAY"
    assert c["severity"] == "soft"


def test_rule5_schedule_no_dates_skipped():
    """Schedule records with no dates are skipped."""
    records = [
        {"member": "Alice", "category": "Schedule", "stance": "positive", "value": {"start_date": None, "end_date": None, "time_of_day": "morning"}},
        {"member": "Bob", "category": "Schedule", "stance": "positive", "value": {"start_date": None, "end_date": None, "time_of_day": "afternoon"}},
    ]
    assert len(detect_conflicts(records)) == 0


def test_proposal_example_3_members_beach_vs_historical_site():
    """ 3 members, beach vs historical site."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Charlie", "category": "Destination", "stance": "positive", "value": {"name": "historical site"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["type"] == "Destination"
    assert c["severity"] == "soft"
    assert c["rule_id"] == "DEST_SOFT"
    assert set(c["members"]) == {"Alice", "Bob", "Charlie"}
    assert set(c["items"]["destinations"]) == {"beach", "historical site"}


def test_synonym_matching_destination_and_activity():
    """Synonyms should map to canonical terms and trigger appropriate conflicts."""
    # Destination synonym: "nuwaraeliya" vs "Nuwara Eliya"
    records_dest = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "nuwaraeliya"}},
        {"member": "Bob", "category": "Destination", "stance": "negative", "value": {"name": "nuwara eliya"}},
    ]
    conflicts_dest = detect_conflicts(records_dest)
    assert len(conflicts_dest) == 1
    assert conflicts_dest[0]["rule_id"] == "DEST_HARD"
    assert conflicts_dest[0]["items"]["destination"] == "nuwara eliya"

    # Activity synonym: "trekking" vs "hike" -> canonical "hiking"
    records_act = [
        {"member": "Alice", "category": "Activity", "stance": "positive", "value": {"name": "trekking"}},
        {"member": "Bob", "category": "Activity", "stance": "negative", "value": {"name": "hike"}},
    ]
    conflicts_act = detect_conflicts(records_act)
    assert len(conflicts_act) == 1
    assert conflicts_act[0]["rule_id"] == "ACTIVITY_HARD"
    assert conflicts_act[0]["items"]["activity"] == "hiking"


def test_self_contradiction_uses_latest_and_logs_warning(caplog):
    """Member's own contradictory records: only latest is kept, warning logged."""
    with caplog.at_level(logging.WARNING):
        records = [
            {"member": "Alice", "category": "Destination", "stance": "negative", "value": {"name": "ella"}},
            {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},  # Latest
            {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        ]
        conflicts = detect_conflicts(records)

    # Bob and Alice both ended up positive about ella, so no hard conflict!
    assert len(conflicts) == 0
    assert any("contradictory/multiple records" in record.message for record in caplog.records)


def test_one_member_returns_empty():
    """Single member should return empty list."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Alice", "category": "Activity", "stance": "positive", "value": {"name": "hiking"}},
    ]
    assert detect_conflicts(records) == []


def test_empty_input_returns_empty():
    """Empty list returns empty list."""
    assert detect_conflicts([]) == []


def test_bad_input_raises_validation_error():
    """Invalid category, bounds, or dates must raise validation errors."""
    # Invalid category
    with pytest.raises(ValidationError):
        detect_conflicts([{"member": "Alice", "category": "UnknownCategory", "stance": "positive", "value": {"name": "ella"}}])

    # Budget min > max
    with pytest.raises(ValidationError):
        detect_conflicts([{"member": "Alice", "category": "Budget", "stance": "positive", "value": {"min": 5000.0, "max": 2000.0, "currency": "LKR", "scope": "per_person"}}])

    # Schedule invalid date format
    with pytest.raises(ValidationError):
        detect_conflicts([{"member": "Alice", "category": "Schedule", "stance": "positive", "value": {"start_date": "11-01-2026"}}])

    # Destination empty name
    with pytest.raises(ValidationError):
        detect_conflicts([{"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "   "}}])


def test_ignored_categories_do_not_produce_conflicts():
    """Food, Accommodation, Transport, Travel Style are ignored for now."""
    records = [
        {"member": "Alice", "category": "Food", "stance": "positive", "value": {"name": "seafood"}},
        {"member": "Bob", "category": "Food", "stance": "negative", "value": {"name": "seafood"}},
        {"member": "Alice", "category": "Accommodation", "stance": "positive", "value": {"type": "hotel"}},
        {"member": "Bob", "category": "Accommodation", "stance": "positive", "value": {"type": "villa"}},
    ]
    conflicts = detect_conflicts(records)
    assert len(conflicts) == 0
