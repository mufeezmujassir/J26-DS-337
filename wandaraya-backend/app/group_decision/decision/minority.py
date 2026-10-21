"""Minority Preference Protection and Compromise Generator (Step 10d).

Principle:
Minority protection must give a minority member's important preference
representation WITHOUT overriding the majority. The weighted winner always stays
in the plan, and a compromise is a plan skeleton, not a route. Real-world feasibility
(distance, opening hours, transport) is handled elsewhere and must not be invented here.
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path
from typing import Any
import yaml

from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.decision.baselines import METHODS, _deduplicate_records, set_seed
from app.group_decision.decision.metrics import (
    member_satisfaction,
    member_satisfaction_plan,
    min_member_satisfaction,
    min_member_satisfaction_plan,
    preference_coverage,
    preference_coverage_plan,
)
from app.group_decision.decision.schemas import DecisionResult, PreferenceRecord
from app.group_decision.decision.weighted import load_weighted_config, weighted_vote

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "config.yaml"
DEFAULT_HINTS_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "compromise_hints.yaml"


def load_minority_config(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate minority protection configuration."""
    base_cfg = load_weighted_config(config_path)

    minority_defaults: dict[str, Any] = {
        "enabled": True,
        "base_method": "weighted",
        "min_strength": 1.0,
        "slots": {
            "Destination": ["stop_1", "stop_2", "stop_3"],
            "Activity": ["morning", "afternoon", "evening"],
        },
        "max_protection_items": None,
        "solver": "greedy",
        "allow_repeats": False,
        "forbid_rejected_items": True,
        "hints_path": "configs/compromise_hints.yaml",
    }

    raw_min = base_cfg.get("minority", {})
    for k, v in minority_defaults.items():
        if k not in raw_min:
            raw_min[k] = v

    if overrides:
        if "minority" in overrides and isinstance(overrides["minority"], dict):
            raw_min.update(overrides["minority"])
        for k in minority_defaults.keys():
            if k in overrides:
                raw_min[k] = overrides[k]
        for k, v in overrides.items():
            if k != "minority" and k not in minority_defaults:
                base_cfg[k] = v

    # Validate config
    min_str = raw_min.get("min_strength", 1.0)
    if not isinstance(min_str, (int, float)) or min_str < 0:
        raise ValueError(f"Invalid min_strength '{min_str}': min_strength must be >= 0.")

    solver = raw_min.get("solver", "greedy")
    if solver not in ("greedy", "exact"):
        raise ValueError(f"Unknown solver '{solver}'. Allowed: 'greedy', 'exact'.")

    slots_cfg = raw_min.get("slots")
    if isinstance(slots_cfg, list):
        if len(slots_cfg) < 1:
            raise ValueError("slots must have length >= 1.")
    elif isinstance(slots_cfg, int):
        if slots_cfg < 1:
            raise ValueError("slots must be >= 1.")
    elif isinstance(slots_cfg, dict):
        for cat, sl_list in slots_cfg.items():
            if (isinstance(sl_list, list) and len(sl_list) < 1) or (isinstance(sl_list, int) and sl_list < 1):
                raise ValueError(f"slots for category '{cat}' must have length >= 1.")

    base_cfg["minority"] = raw_min
    return base_cfg


def load_compromise_hints(hints_path: str | Path | None = None) -> dict[str, dict[str, str]]:
    """Load soft ordering slot hints from YAML file."""
    path = Path(hints_path) if hints_path else DEFAULT_HINTS_PATH
    if not path.is_file():
        fallback = Path("configs/compromise_hints.yaml")
        if fallback.is_file():
            path = fallback
        else:
            return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("Failed loading compromise hints from %s: %s", path, e)
    return {}


def _get_slots_for_category(slots_cfg: Any, category: str) -> list[str]:
    """Retrieve slot names list for a given category."""
    if isinstance(slots_cfg, list):
        return [str(s) for s in slots_cfg]
    if isinstance(slots_cfg, int):
        return [f"slot_{i+1}" for i in range(slots_cfg)]
    if isinstance(slots_cfg, dict):
        cat_slots = slots_cfg.get(category)
        if isinstance(cat_slots, list):
            return [str(s) for s in cat_slots]
        if isinstance(cat_slots, int):
            return [f"slot_{i+1}" for i in range(cat_slots)]
    # Defaults
    if category == "Activity":
        return ["morning", "afternoon", "evening"]
    return ["stop_1", "stop_2", "stop_3"]


def protect_minority(
    records: list[Any],
    config: dict[str, Any] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    allowed_options: list[str] | None = None,
    category: str = "Destination",
    candidate_options: list[str] | None = None,
    **kwargs: Any,
) -> DecisionResult:
    """Method 4: Minority preference protection and compromise generator.

    Generates a compromise plan skeleton that preserves the majority/weighted winner
    in the primary slot and includes representative options for protected minority members.

    Args:
        records: List of structured preference records.
        config: Optional configuration dictionary.
        conflicts: Optional list of conflict dictionaries from conflict detector.
        allowed_options: Optional whitelist of candidate option strings.
        category: Decision category ('Destination' or 'Activity').
        candidate_options: Optional candidate options list (from decide() interface).

    Returns:
        DecisionResult instance with full plan skeleton, explainability, and comparative metrics.
    """
    set_seed(42)

    # Resolve options filter
    effective_allowed = allowed_options or candidate_options or kwargs.get("candidate_options")

    # Resolve conflicts
    effective_conflicts = conflicts
    if effective_conflicts is None and config and isinstance(config, dict):
        effective_conflicts = config.get("conflicts")

    # 1. Load configuration
    cfg = load_minority_config(overrides=config)
    m_cfg = cfg.get("minority", {})

    enabled = bool(m_cfg.get("enabled", True))
    base_method_name = str(m_cfg.get("base_method", "weighted"))
    min_strength = float(m_cfg.get("min_strength", 1.0))
    solver = str(m_cfg.get("solver", "greedy"))
    allow_repeats = bool(m_cfg.get("allow_repeats", False))
    forbid_rejected_items = bool(m_cfg.get("forbid_rejected_items", True))
    hints_path = m_cfg.get("hints_path")

    # Determine slots
    slots_list = _get_slots_for_category(m_cfg.get("slots"), category)
    if not slots_list:
        slots_list = ["stop_1", "stop_2", "stop_3"]

    max_prot_raw = m_cfg.get("max_protection_items")
    max_protection_items = (
        int(max_prot_raw) if max_prot_raw is not None else max(0, len(slots_list) - 1)
    )

    # 2. Run Base Decision Method (Primary Decision)
    if base_method_name not in METHODS:
        base_method_name = "weighted"
    base_method_fn = METHODS[base_method_name]

    base_result = base_method_fn(
        records=records,
        category=category,
        candidate_options=effective_allowed,
        config=cfg,
    )

    # If minority protection is disabled, return base method result immediately
    if not enabled:
        return base_result

    primary_option = base_result.chosen_option

    # Edge Case: Empty records or no primary option found
    if not records or primary_option is None:
        base_dict = base_result.model_dump()
        base_dict.update({
            "method": "weighted_minority",
            "primary_option": None,
            "protected_members": [],
            "plan": [],
            "covered_members": [],
            "uncovered_members": [],
            "protection_applied": False,
            "resolved_conflicts": [],
            "unresolved_conflicts": effective_conflicts or [],
            "unresolved_rejection": [],
            "explanation": ["No primary option chosen; minority protection not applied."],
            "metrics": {
                "coverage_before": 0.0,
                "coverage_after": 0.0,
                "min_satisfaction_before": 0.0,
                "min_satisfaction_after": 0.0,
                "plan_size": 0,
            },
        })
        return DecisionResult.model_validate(base_dict)

    # 3. Member preferences and deduplication
    active_records, mention_order = _deduplicate_records(records, category)

    all_members: set[str] = set()
    member_liked: dict[str, list[str]] = {}
    member_rejected: dict[str, list[str]] = {}
    member_all_stances: dict[str, dict[str, str]] = {}

    for rec in active_records:
        val = rec.value
        opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
        if not opt_raw:
            continue
        c_opt = normalize_name(opt_raw, category=category)
        m = rec.member
        all_members.add(m)

        if m not in member_liked:
            member_liked[m] = []
            member_rejected[m] = []
            member_all_stances[m] = {}

        member_all_stances[m][c_opt] = rec.stance
        if rec.stance == "positive" and c_opt not in member_liked[m]:
            member_liked[m].append(c_opt)
        elif rec.stance == "negative" and c_opt not in member_rejected[m]:
            member_rejected[m].append(c_opt)

    canon_primary = normalize_name(primary_option, category=category)

    # 4. Step 1: Find Protected Members
    # A member is covered if the primary option is positive for them
    covered_by_primary = {
        m for m in all_members if member_all_stances.get(m, {}).get(canon_primary) == "positive"
    }
    uncovered_candidates = [m for m in sorted(all_members) if m not in covered_by_primary]

    # Map member -> highest vote weight on any liked option
    member_strengths: dict[str, float] = {}
    contributions = base_result.contributions or []
    for m in all_members:
        liked_weights = [
            c["weight"] for c in contributions
            if c.get("member") == m and c.get("stance") == "positive"
        ]
        member_strengths[m] = max(liked_weights) if liked_weights else 1.0

    protected_members: list[dict[str, Any]] = []
    for m in uncovered_candidates:
        str_val = member_strengths.get(m, 1.0)
        if str_val >= min_strength:
            # Determine reason
            if canon_primary in member_rejected.get(m, []):
                reason_code = "rejected_primary"
            else:
                reason_code = "preference_not_chosen"

            protected_members.append({
                "member": m,
                "reason": reason_code,
                "strength": round(str_val, 4),
                "preferred_options": list(member_liked.get(m, [])),
            })

    # Metrics before protection
    cov_before = preference_coverage(records, canon_primary, category=category)
    min_sat_before = min_member_satisfaction(records, canon_primary, category=category)

    # If every member is already covered by primary option or no protected members
    if not protected_members:
        plan = [{"slot": slots_list[0], "item": canon_primary, "reason": "majority_winner"}]
        explanation = ["All members are covered by primary option; minority protection not needed."]
        cov_after = preference_coverage_plan(records, [canon_primary], category=category)
        min_sat_after = min_member_satisfaction_plan(records, [canon_primary], category=category)

        # Conflict resolution check
        res_conflicts, unres_conflicts, unres_rejections = _evaluate_conflicts(
            effective_conflicts, [canon_primary], member_rejected, slots_list[:1]
        )

        base_dict = base_result.model_dump()
        base_dict.update({
            "method": "weighted_minority",
            "primary_option": canon_primary,
            "chosen_option": canon_primary,
            "protected_members": [],
            "plan": plan,
            "covered_members": sorted(list(covered_by_primary)),
            "uncovered_members": [],
            "protection_applied": False,
            "resolved_conflicts": res_conflicts,
            "unresolved_conflicts": unres_conflicts,
            "unresolved_rejection": unres_rejections,
            "explanation": explanation,
            "metrics": {
                "coverage_before": cov_before,
                "coverage_after": cov_after,
                "min_satisfaction_before": min_sat_before,
                "min_satisfaction_after": min_sat_after,
                "plan_size": 1,
            },
        })
        return DecisionResult.model_validate(base_dict)

    # 5. Step 2: Build the Compromise Plan Skeleton
    # Free slots available for minority protection items
    free_slot_names = slots_list[1:]
    allowed_free_slots_count = min(len(free_slot_names), max_protection_items)

    # Candidate options gathering
    all_mentioned_options: list[str] = list(mention_order)
    if effective_allowed:
        allowed_canon = {normalize_name(opt, category=category) for opt in effective_allowed}
        all_mentioned_options = [opt for opt in all_mentioned_options if opt in allowed_canon]

    candidate_items = [opt for opt in all_mentioned_options if opt != canon_primary or allow_repeats]

    # Item rejection filtering rule:
    # Do not add an item that any member rejects, unless every candidate for an uncovered member is rejected by someone
    global_rejected_items = {
        opt for m, rej_list in member_rejected.items() for opt in rej_list
    }

    # Candidates specifically liked by uncovered protected members
    uncovered_liked_options = {
        opt for pm in protected_members for opt in pm["preferred_options"]
        if opt != canon_primary
    }

    if forbid_rejected_items:
        clean_uncovered_liked = [
            opt for opt in uncovered_liked_options if opt not in global_rejected_items
        ]
        if clean_uncovered_liked:
            eligible_candidates = clean_uncovered_liked
        else:
            # Fallback: all candidates for uncovered members are rejected by someone
            eligible_candidates = list(uncovered_liked_options)
    else:
        eligible_candidates = list(uncovered_liked_options)

    # 6. Solvers: Greedy vs Exact
    selected_minority_items: list[str] = []

    if allowed_free_slots_count > 0 and eligible_candidates:
        if solver == "exact" and len(eligible_candidates) <= 8:
            selected_minority_items = _solve_exact(
                records=records,
                primary_item=canon_primary,
                candidates=eligible_candidates,
                protected_members=protected_members,
                max_slots=allowed_free_slots_count,
                category=category,
                base_scores=base_result.scores,
            )
        else:
            if solver == "exact" and len(eligible_candidates) > 8:
                logger.info(
                    "Exact solver requested with %d candidates (> 8); falling back to greedy.",
                    len(eligible_candidates),
                )
            selected_minority_items = _solve_greedy(
                candidates=eligible_candidates,
                protected_members=protected_members,
                max_slots=allowed_free_slots_count,
                base_scores=base_result.scores,
            )

    # 7. Safe Alternative: for eligible members who only rejected primary (liked nothing)
    # If free slots remain, add best-ranked option that this member does not reject
    slots_remaining = allowed_free_slots_count - len(selected_minority_items)
    safe_alternative_items: list[str] = []

    if slots_remaining > 0:
        members_rejecting_primary_only = [
            pm["member"] for pm in protected_members if not pm["preferred_options"]
        ]
        for m in members_rejecting_primary_only:
            if slots_remaining <= 0:
                break
            m_rejections = set(member_rejected.get(m, []))
            # Find candidate not rejected by member m
            potential_safe = [
                opt for opt in all_mentioned_options
                if opt != canon_primary
                and opt not in selected_minority_items
                and opt not in safe_alternative_items
                and opt not in m_rejections
            ]
            if forbid_rejected_items:
                clean_safe = [opt for opt in potential_safe if opt not in global_rejected_items]
                candidates_safe = clean_safe if clean_safe else potential_safe
            else:
                candidates_safe = potential_safe

            if candidates_safe:
                # Rank by base score descending, then alphabetical
                best_safe = sorted(
                    candidates_safe,
                    key=lambda opt: (-base_result.scores.get(opt, 0.0), opt),
                )[0]
                safe_alternative_items.append(best_safe)
                slots_remaining -= 1

    # 8. Slot Ordering and Compromise Hints
    # Slot order: primary first, then remaining items by descending strength
    all_compromise_items = selected_minority_items + safe_alternative_items
    item_reasons: dict[str, str] = {canon_primary: "majority_winner"}
    for item in selected_minority_items:
        item_reasons[item] = "minority_protection"
    for item in safe_alternative_items:
        item_reasons[item] = "safe_alternative"

    # Compute item strength for ordering: max strength of members liking this item
    item_strengths: dict[str, float] = {}
    for item in all_compromise_items:
        supporters_str = [
            member_strengths[m] for m in all_members
            if member_all_stances.get(m, {}).get(item) == "positive"
        ]
        item_strengths[item] = max(supporters_str) if supporters_str else 1.0

    # Sort remaining items by descending strength, then base score, then alphabetical
    sorted_remaining = sorted(
        all_compromise_items,
        key=lambda it: (-item_strengths.get(it, 1.0), -base_result.scores.get(it, 0.0), it),
    )

    # Apply soft time hints from compromise_hints.yaml
    hints = load_compromise_hints(hints_path).get(category, {})
    final_ordered_items = [canon_primary] + sorted_remaining

    # Build plan assignments to slots
    plan: list[dict[str, Any]] = []
    # If slots are time of day (morning, afternoon, evening), use hints where applicable
    if set(slots_list).intersection({"morning", "afternoon", "evening"}):
        plan = _assign_slots_with_hints(
            primary_item=canon_primary,
            remaining_items=sorted_remaining,
            available_slots=slots_list,
            hints=hints,
            item_reasons=item_reasons,
        )
    else:
        # Standard sequential slot assignment
        for idx, item in enumerate(final_ordered_items[:len(slots_list)]):
            plan.append({
                "slot": slots_list[idx],
                "item": item,
                "reason": item_reasons.get(item, "minority_protection"),
            })

    plan_item_names = [p["item"] for p in plan]

    # 9. Covered and Uncovered Member Lists
    covered_members: list[str] = []
    for m in sorted(all_members):
        if any(member_all_stances.get(m, {}).get(it) == "positive" for it in plan_item_names):
            covered_members.append(m)

    uncovered_members: list[dict[str, Any]] = []
    for pm in protected_members:
        m = pm["member"]
        if m not in covered_members:
            uncovered_members.append({
                "member": m,
                "reason": "no_slot_available",
                "strength": pm["strength"],
                "preferred_options": pm["preferred_options"],
            })

    # 10. Conflict Resolution Reporting
    res_conflicts, unres_conflicts, unres_rejections = _evaluate_conflicts(
        conflicts=effective_conflicts,
        plan_items=plan_item_names,
        member_rejected=member_rejected,
        slots_assigned=[p["slot"] for p in plan],
    )

    # 11. Comparative Metrics & Explanation
    cov_after = preference_coverage_plan(records, plan_item_names, category=category)
    min_sat_after = min_member_satisfaction_plan(records, plan_item_names, category=category)
    protection_applied = len(plan_item_names) > 1

    explanation: list[str] = [
        f"Primary winner '{canon_primary}' assigned to slot '{plan[0]['slot']}' ({plan[0]['reason']})."
    ]
    if protection_applied:
        for p in plan[1:]:
            explanation.append(
                f"Minority compromise: '{p['item']}' assigned to slot '{p['slot']}' ({p['reason']})."
            )
        explanation.append(
            f"Coverage improved from {cov_before:.2f} to {cov_after:.2f}; "
            f"minimum satisfaction changed from {min_sat_before:.2f} to {min_sat_after:.2f}."
        )
    else:
        explanation.append("No additional compromise items added to the plan.")

    base_dict = base_result.model_dump()
    base_dict.update({
        "method": "weighted_minority",
        "primary_option": canon_primary,
        "chosen_option": canon_primary,
        "protected_members": protected_members,
        "plan": plan,
        "covered_members": covered_members,
        "uncovered_members": uncovered_members,
        "protection_applied": protection_applied,
        "resolved_conflicts": res_conflicts,
        "unresolved_conflicts": unres_conflicts,
        "unresolved_rejection": unres_rejections,
        "explanation": explanation,
        "metrics": {
            "coverage_before": cov_before,
            "coverage_after": cov_after,
            "min_satisfaction_before": min_sat_before,
            "min_satisfaction_after": min_sat_after,
            "plan_size": len(plan),
        },
    })
    return DecisionResult.model_validate(base_dict)


def _solve_greedy(
    candidates: list[str],
    protected_members: list[dict[str, Any]],
    max_slots: int,
    base_scores: dict[str, float],
) -> list[str]:
    """Greedy selection of compromise items maximizing newly covered members."""
    selected: list[str] = []
    uncovered = set(
        pm["member"] for pm in protected_members if pm.get("preferred_options")
    )
    member_liked_map = {pm["member"]: set(pm.get("preferred_options", [])) for pm in protected_members}
    member_str_map = {pm["member"]: pm.get("strength", 1.0) for pm in protected_members}

    for _ in range(max_slots):
        available = [c for c in candidates if c not in selected]
        if not available or not uncovered:
            break

        best_cand: str | None = None
        best_score_tuple = (-1, -1.0, -1.0, "")

        for cand in available:
            newly_covered = {m for m in uncovered if cand in member_liked_map.get(m, set())}
            cov_count = len(newly_covered)
            tot_strength = sum(member_str_map[m] for m in newly_covered)
            b_score = base_scores.get(cand, 0.0)

            # Maximize coverage, then strength, then base_score, then alphabetical (smaller cand is better)
            # In Python, tuple comparison: we use negative cand name for alphabetical tie break
            score_tuple = (cov_count, tot_strength, b_score, cand)
            if best_cand is None:
                best_cand = cand
                best_score_tuple = score_tuple
            else:
                # Compare: first 3 ascending (we want larger), cand ascending (we want alphabetical smaller)
                is_better = (
                    (score_tuple[0] > best_score_tuple[0]) or
                    (score_tuple[0] == best_score_tuple[0] and score_tuple[1] > best_score_tuple[1]) or
                    (score_tuple[0] == best_score_tuple[0] and score_tuple[1] == best_score_tuple[1] and score_tuple[2] > best_score_tuple[2]) or
                    (score_tuple[0] == best_score_tuple[0] and score_tuple[1] == best_score_tuple[1] and score_tuple[2] == best_score_tuple[2] and cand < best_score_tuple[3])
                )
                if is_better:
                    best_cand = cand
                    best_score_tuple = score_tuple

        if best_cand is None or best_score_tuple[0] == 0:
            break

        selected.append(best_cand)
        uncovered -= {m for m in uncovered if best_cand in member_liked_map.get(m, set())}

    return selected


def _solve_exact(
    records: list[Any],
    primary_item: str,
    candidates: list[str],
    protected_members: list[dict[str, Any]],
    max_slots: int,
    category: str,
    base_scores: dict[str, float],
) -> list[str]:
    """Exact solver trying all subsets up to max_slots to optimize coverage, min sat, and strength."""
    member_liked_map = {pm["member"]: set(pm.get("preferred_options", [])) for pm in protected_members}
    member_str_map = {pm["member"]: pm.get("strength", 1.0) for pm in protected_members}

    best_subset: list[str] = []
    best_key = (-1, -1.0, -1.0, ())

    # Iterate through subset sizes from 1 to max_slots
    for k in range(1, min(len(candidates), max_slots) + 1):
        for combo in itertools.combinations(sorted(candidates), k):
            subset = list(combo)
            plan_items = [primary_item] + subset

            # 1. Coverage of protected members
            covered = {
                pm["member"] for pm in protected_members
                if any(it in member_liked_map.get(pm["member"], set()) for it in subset)
            }
            cov_count = len(covered)

            # 2. Minimum member satisfaction
            min_sat = min_member_satisfaction_plan(records, plan_items, category=category)

            # 3. Total strength of covered members
            tot_str = sum(member_str_map[m] for m in covered)

            # Tie-break key
            # Higher coverage -> higher min_sat -> higher strength -> alphabetical earlier combo
            if cov_count > best_key[0]:
                best_subset = subset
                best_key = (cov_count, min_sat, tot_str, combo)
            elif cov_count == best_key[0]:
                if min_sat > best_key[1]:
                    best_subset = subset
                    best_key = (cov_count, min_sat, tot_str, combo)
                elif min_sat == best_key[1]:
                    if tot_str > best_key[2]:
                        best_subset = subset
                        best_key = (cov_count, min_sat, tot_str, combo)
                    elif tot_str == best_key[2]:
                        if combo < best_key[3]:
                            best_subset = subset
                            best_key = (cov_count, min_sat, tot_str, combo)

    return best_subset


def _assign_slots_with_hints(
    primary_item: str,
    remaining_items: list[str],
    available_slots: list[str],
    hints: dict[str, str],
    item_reasons: dict[str, str],
) -> list[dict[str, Any]]:
    """Assign items to time-based slots respecting soft ordering hints."""
    slot_assignments: dict[str, dict[str, Any]] = {}
    unassigned_slots = list(available_slots)

    # 1. Primary option gets first slot or hinted slot if free
    primary_hint = hints.get(primary_item)
    if primary_hint and primary_hint in unassigned_slots:
        slot_assignments[primary_hint] = {
            "slot": primary_hint,
            "item": primary_item,
            "reason": item_reasons.get(primary_item, "majority_winner"),
        }
        unassigned_slots.remove(primary_hint)
    else:
        first_slot = unassigned_slots[0]
        slot_assignments[first_slot] = {
            "slot": first_slot,
            "item": primary_item,
            "reason": item_reasons.get(primary_item, "majority_winner"),
        }
        unassigned_slots.remove(first_slot)

    # 2. Remaining items with hints
    pending_items = []
    for item in remaining_items:
        h = hints.get(item)
        if h and h in unassigned_slots:
            slot_assignments[h] = {
                "slot": h,
                "item": item,
                "reason": item_reasons.get(item, "minority_protection"),
            }
            unassigned_slots.remove(h)
        else:
            pending_items.append(item)

    # 3. Assign any remaining items to remaining unassigned slots
    for item in pending_items:
        if not unassigned_slots:
            break
        s = unassigned_slots.pop(0)
        slot_assignments[s] = {
            "slot": s,
            "item": item,
            "reason": item_reasons.get(item, "minority_protection"),
        }

    # Order by original slots order
    ordered_plan = [slot_assignments[s] for s in available_slots if s in slot_assignments]
    return ordered_plan


def _evaluate_conflicts(
    conflicts: list[dict[str, Any]] | None,
    plan_items: list[str],
    member_rejected: dict[str, list[str]],
    slots_assigned: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Report resolved vs unresolved conflicts and explicit unresolved rejections."""
    resolved_conflicts: list[dict[str, Any]] = []
    unresolved_conflicts: list[dict[str, Any]] = []
    unresolved_rejections: list[dict[str, Any]] = []

    plan_items_set = set(plan_items)

    if conflicts:
        for c in conflicts:
            c_dict = dict(c)
            c_type = c.get("type")
            c_sev = c.get("severity")
            c_items = c.get("items", {})

            # Extract conflict item options
            conf_opts: list[str] = []
            if isinstance(c_items, dict):
                # E.g. {"member1_options": [...], "member2_options": [...]} or {"options": [...]}
                for v in c_items.values():
                    if isinstance(v, list):
                        conf_opts.extend([normalize_name(str(x)) for x in v])
                    elif isinstance(v, str):
                        conf_opts.append(normalize_name(v))
            elif isinstance(c_items, list):
                conf_opts.extend([normalize_name(str(x)) for x in c_items])

            # A soft Destination or Activity conflict is resolved when both options are in the plan
            # A hard conflict is NEVER marked resolved
            if c_sev == "soft" and c_type in ("Destination", "Activity") and len(conf_opts) >= 2:
                if all(opt in plan_items_set for opt in conf_opts):
                    resolved_conflicts.append(c_dict)
                    continue

            unresolved_conflicts.append(c_dict)

    # Check for members who rejected an item in the plan
    for m, rejs in member_rejected.items():
        for idx, item in enumerate(plan_items):
            if item in rejs:
                slot_name = slots_assigned[idx] if idx < len(slots_assigned) else f"slot_{idx+1}"
                unresolved_rejections.append({
                    "member": m,
                    "rejected_item": item,
                    "slot": slot_name,
                })

    return resolved_conflicts, unresolved_conflicts, unresolved_rejections


# Register in METHODS registry
METHODS["weighted_minority"] = protect_minority
