"""Consensus Level and Fairness Metrics (Step 10e).

PRINCIPLE:
consensus is an OUTCOME measure of how acceptable the final decision is to
the whole group, not the share of votes the winner received. It uses the same
stance information as the decision, so it is a consistency and fairness
indicator, not independent evidence that the decision is correct.

Extends src/decision/. Reuses PreferenceRecord, normalize_name, DecisionResult,
the METHODS registry, plan-level metric functions from src.decision.metrics,
weighted contributions from src.decision.weighted, and the conflict list format
from src.conflict.rules.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import yaml

from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.decision.baselines import METHODS, decide, load_decision_config, set_seed
from app.group_decision.decision.metrics import (
    _deduplicate_records,
    member_satisfaction_plan,
    preference_coverage_plan,
    min_member_satisfaction_plan,
    satisfaction_gap,
)
from app.group_decision.decision.schemas import (
    ConflictSummary,
    ConsensusCategoryResult,
    ConsensusResult,
    DecisionResult,
    PreferenceRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "config.yaml"


def load_consensus_config(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load consensus configuration parameters from config.yaml with defaults.

    Args:
        config_path: Optional path to YAML config file.
        overrides: Optional dict of parameter overrides.

    Returns:
        Validated consensus configuration dictionary.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    defaults: dict[str, Any] = {
        "lambda": 0.5,
        "weight_by_vote_weight": False,
        "high_threshold": 0.75,
        "medium_threshold": 0.50,
        "reach_threshold": 0.75,
        "min_acceptance_threshold": 0.50,
        "participants_only": False,
        "conflict_penalty": 0.0,
        "max_conflict_penalty": 0.30,
    }

    cfg: dict[str, Any] = dict(defaults)

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            file_cfg = data.get("decision", {}).get("consensus", {})
            if isinstance(file_cfg, dict):
                cfg.update(file_cfg)
        except Exception as e:
            logger.warning("Error loading consensus config from %s: %s. Using defaults.", path, e)
    else:
        # Fallback to local configs/config.yaml if relative
        fallback = Path("configs/config.yaml")
        if fallback.exists():
            try:
                with open(fallback, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                file_cfg = data.get("decision", {}).get("consensus", {})
                if isinstance(file_cfg, dict):
                    cfg.update(file_cfg)
            except Exception:
                pass

    if overrides:
        # Check both top-level and nested 'consensus' overrides
        if "consensus" in overrides and isinstance(overrides["consensus"], dict):
            cfg.update(overrides["consensus"])
        cfg.update({k: v for k, v in overrides.items() if k != "consensus" and k in defaults})

    validate_consensus_config(cfg)
    return cfg


def validate_consensus_config(cfg: dict[str, Any]) -> None:
    """Validate consensus configuration constraints.

    Rules:
        - 0 <= lambda <= 1
        - 0 <= medium_threshold <= high_threshold <= 1
        - 0 <= reach_threshold <= 1
        - 0 <= min_acceptance_threshold <= 1
        - conflict_penalty >= 0
        - max_conflict_penalty >= 0

    Raises:
        ValueError if any parameter violates constraints.
    """
    lam = cfg.get("lambda", 0.5)
    if not isinstance(lam, (int, float)) or not (0.0 <= float(lam) <= 1.0):
        raise ValueError(f"Invalid lambda '{lam}': lambda must be a float between 0.0 and 1.0.")

    high_th = cfg.get("high_threshold", 0.75)
    med_th = cfg.get("medium_threshold", 0.50)
    if not isinstance(high_th, (int, float)) or not (0.0 <= float(high_th) <= 1.0):
        raise ValueError(f"Invalid high_threshold '{high_th}': must be between 0.0 and 1.0.")
    if not isinstance(med_th, (int, float)) or not (0.0 <= float(med_th) <= 1.0):
        raise ValueError(f"Invalid medium_threshold '{med_th}': must be between 0.0 and 1.0.")
    if float(med_th) > float(high_th):
        raise ValueError(f"medium_threshold ({med_th}) cannot exceed high_threshold ({high_th}).")

    reach_th = cfg.get("reach_threshold", 0.75)
    if not isinstance(reach_th, (int, float)) or not (0.0 <= float(reach_th) <= 1.0):
        raise ValueError(f"Invalid reach_threshold '{reach_th}': must be between 0.0 and 1.0.")

    min_acc_th = cfg.get("min_acceptance_threshold", 0.50)
    if not isinstance(min_acc_th, (int, float)) or not (0.0 <= float(min_acc_th) <= 1.0):
        raise ValueError(
            f"Invalid min_acceptance_threshold '{min_acc_th}': must be between 0.0 and 1.0."
        )

    conf_pen = cfg.get("conflict_penalty", 0.0)
    if not isinstance(conf_pen, (int, float)) or float(conf_pen) < 0.0:
        raise ValueError(f"Invalid conflict_penalty '{conf_pen}': must be >= 0.")

    max_pen = cfg.get("max_conflict_penalty", 0.30)
    if not isinstance(max_pen, (int, float)) or float(max_pen) < 0.0:
        raise ValueError(f"Invalid max_conflict_penalty '{max_pen}': must be >= 0.")


def compute_gini(values: list[float] | dict[str, float]) -> float:
    """Calculate the Gini coefficient of inequality for member acceptance scores.

    Formula:
        G = sum_i sum_j |a_i - a_j| / (2 * n * sum_i a_i)

    Returns:
        float in [0.0, 1.0]. Returns 0.0 if n <= 1 or total sum <= 0.
    """
    if isinstance(values, dict):
        vals = [float(v) for v in values.values()]
    else:
        vals = [float(v) for v in values]

    n = len(vals)
    if n <= 1:
        return 0.0
    total = sum(vals)
    if total <= 0.0:
        return 0.0

    diff_sum = sum(abs(x - y) for x in vals for y in vals)
    gini = diff_sum / (2.0 * n * total)
    return round(float(gini), 4)


def _extract_plan_items(result: DecisionResult) -> list[str]:
    """Extract list of option item names from decision result."""
    if result.plan:
        items: list[str] = []
        for p in result.plan:
            if isinstance(p, dict):
                raw = p.get("item") or p.get("name")
            else:
                raw = p
            if raw:
                items.append(normalize_name(str(raw), category=result.category))
        if items:
            return items

    if result.chosen_option:
        return [normalize_name(result.chosen_option, category=result.category)]
    return []


def _summarize_conflicts(
    conflicts: list[Any] | None,
    category: str,
    plan_items: list[str],
    records: list[Any],
    result: DecisionResult | None = None,
) -> dict[str, Any]:
    """Summarize conflict status into resolved_soft, unresolved_soft, unresolved_hard, and unresolved_rejections."""
    plan_set = set(normalize_name(it, category=category) for it in plan_items)

    # 1. Member rejections on items in the plan
    member_rejections = _deduplicate_records(records, category=category)
    unresolved_rejection_members: set[str] = set()
    for m, stances in member_rejections.items():
        for opt, st in stances.items():
            if st == "negative" and opt in plan_set:
                unresolved_rejection_members.add(m)

    # If result already has unresolved_rejection list, include them as well
    if result and getattr(result, "unresolved_rejection", None):
        for rej in result.unresolved_rejection:
            if isinstance(rej, dict) and "member" in rej:
                unresolved_rejection_members.add(rej["member"])

    resolved_soft = 0
    unresolved_soft = 0
    unresolved_hard = 0

    effective_conflicts = conflicts
    if effective_conflicts is None and result:
        # Fall back to conflicts stored on result if available
        res_conf = getattr(result, "resolved_conflicts", [])
        unres_conf = getattr(result, "unresolved_conflicts", [])
        resolved_soft = len(res_conf) if res_conf else 0
        unresolved_soft = sum(1 for c in unres_conf if (c.get("severity") if isinstance(c, dict) else getattr(c, "severity", None)) == "soft")
        unresolved_hard = sum(1 for c in unres_conf if (c.get("severity") if isinstance(c, dict) else getattr(c, "severity", None)) == "hard")
        return {
            "resolved_soft": resolved_soft,
            "unresolved_soft": unresolved_soft,
            "unresolved_hard": unresolved_hard,
            "unresolved_rejection_members": sorted(list(unresolved_rejection_members)),
        }

    if effective_conflicts:
        for c in effective_conflicts:
            c_dict = c if isinstance(c, dict) else (c.model_dump() if hasattr(c, "model_dump") else getattr(c, "__dict__", {}))
            c_type = c_dict.get("type")
            c_sev = c_dict.get("severity")

            # Only evaluate conflicts matching this category, or general conflicts without type
            if c_type is not None and c_type != category:
                continue

            if c_sev == "hard":
                unresolved_hard += 1
            elif c_sev == "soft":
                # Soft conflicts are resolved if all involved items are present in plan_items
                c_items = c_dict.get("items", {})
                item_names: list[str] = []
                if isinstance(c_items, dict):
                    for v in c_items.values():
                        if isinstance(v, list):
                            item_names.extend([normalize_name(str(x), category=category) for x in v])
                        elif isinstance(v, str):
                            item_names.append(normalize_name(v, category=category))
                elif isinstance(c_items, list):
                    item_names.extend([normalize_name(str(x), category=category) for x in c_items])

                if len(item_names) >= 2 and all(it in plan_set for it in item_names):
                    resolved_soft += 1
                else:
                    unresolved_soft += 1

    return {
        "resolved_soft": resolved_soft,
        "unresolved_soft": unresolved_soft,
        "unresolved_hard": unresolved_hard,
        "unresolved_rejection_members": sorted(list(unresolved_rejection_members)),
    }


def compute_consensus(
    records: list[Any],
    result: DecisionResult | dict[str, DecisionResult] | list[DecisionResult],
    config: dict[str, Any] | None = None,
    conflicts: list[Any] | None = None,
) -> ConsensusResult:
    """Compute consensus level and fairness metrics for a decision outcome.

    Formula:
        acceptance_i = member_satisfaction_plan(records, plan_items)[member]
        mean_acceptance = mean of acceptance_i (equal weights or weighted by vote weight)
        min_acceptance = min of acceptance_i
        consensus_level = lambda * mean_acceptance + (1 - lambda) * min_acceptance
        level_label: "high" if level >= 0.75, "medium" if level >= 0.5, else "low"
        consensus_reached = level >= reach_threshold (0.75) and min_acceptance >= min_acceptance_threshold (0.5)

    Args:
        records: List of preference records.
        result: DecisionResult instance, or dict/list of DecisionResult per category.
        config: Optional consensus configuration overrides.
        conflicts: Optional conflict list from rule-based conflict detector.

    Returns:
        ConsensusResult Pydantic model with per-category and overall metrics.
    """
    set_seed(42)
    cfg = load_consensus_config(overrides=config)

    lambda_param = float(cfg.get("lambda", 0.5))
    weight_by_vote_weight = bool(cfg.get("weight_by_vote_weight", False))
    high_threshold = float(cfg.get("high_threshold", 0.75))
    medium_threshold = float(cfg.get("medium_threshold", 0.50))
    reach_threshold = float(cfg.get("reach_threshold", 0.75))
    min_acc_threshold = float(cfg.get("min_acceptance_threshold", 0.50))
    participants_only = bool(cfg.get("participants_only", False))
    conflict_penalty = float(cfg.get("conflict_penalty", 0.0))
    max_conflict_penalty = float(cfg.get("max_conflict_penalty", 0.30))

    # Normalize input result into mapping category -> DecisionResult
    results_map: dict[str, DecisionResult] = {}
    if isinstance(result, DecisionResult):
        results_map[result.category] = result
    elif isinstance(result, dict):
        for k, v in result.items():
            if isinstance(v, DecisionResult):
                results_map[k] = v
            elif isinstance(v, dict):
                results_map[k] = DecisionResult.model_validate(v)
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, DecisionResult):
                results_map[item.category] = item
            elif isinstance(item, dict):
                r = DecisionResult.model_validate(item)
                results_map[r.category] = r

    categories_skipped: dict[str, str] = {}
    per_category: dict[str, ConsensusCategoryResult] = {}

    for cat, res in results_map.items():
        # Categories with chosen_option None are skipped
        if res.chosen_option is None:
            reason = res.reason or "no_positive_stance"
            categories_skipped[cat] = reason
            continue

        # Filter records if participants_only is True
        if participants_only:
            cat_records = [
                r for r in records
                if (getattr(r, "category", None) or (r.get("category") if isinstance(r, dict) else None)) == cat
            ]
        else:
            cat_records = records

        # 1. Determine plan items
        plan_items = _extract_plan_items(res)
        primary_option = res.primary_option or res.chosen_option
        canon_primary = normalize_name(primary_option, category=cat) if primary_option else None

        # 2. Member acceptance calculation
        acceptance_dict = member_satisfaction_plan(cat_records, plan_items, category=cat)
        members_list = sorted(list(acceptance_dict.keys()))

        trivial_single_member = (len(members_list) == 1)

        # 3. Mean acceptance (unweighted or vote-weight weighted)
        if not members_list:
            mean_acceptance = 0.0
            min_acceptance = 0.0
        else:
            if weight_by_vote_weight:
                member_weights: dict[str, float] = {}
                for c in getattr(res, "contributions", []):
                    m = c.get("member") if isinstance(c, dict) else getattr(c, "member", None)
                    w = c.get("weight") if isinstance(c, dict) else getattr(c, "weight", None)
                    if m and w is not None:
                        member_weights[m] = max(member_weights.get(m, 1.0), float(w))

                weights = [member_weights.get(m, 1.0) for m in members_list]
                acceptances = [acceptance_dict[m] for m in members_list]
                tot_weight = sum(weights)
                if tot_weight > 0:
                    mean_acceptance = sum(w * a for w, a in zip(weights, acceptances)) / tot_weight
                else:
                    mean_acceptance = sum(acceptances) / len(acceptances)
            else:
                mean_acceptance = sum(acceptance_dict.values()) / len(acceptance_dict)

            min_acceptance = min(acceptance_dict.values())

        # 4. Conflict summary and penalty
        conf_summary = _summarize_conflicts(
            conflicts=conflicts,
            category=cat,
            plan_items=plan_items,
            records=cat_records,
            result=res,
        )

        unresolved_hard_count = int(conf_summary.get("unresolved_hard", 0))
        penalty_amount = min(unresolved_hard_count * conflict_penalty, max_conflict_penalty)

        # 5. Consensus level formula
        raw_level = (lambda_param * mean_acceptance) + ((1.0 - lambda_param) * min_acceptance)
        consensus_level = max(0.0, min(1.0, raw_level - penalty_amount))

        # 6. Label and reached check
        if consensus_level >= high_threshold:
            level_label = "high"
        elif consensus_level >= medium_threshold:
            level_label = "medium"
        else:
            level_label = "low"

        consensus_reached = (consensus_level >= reach_threshold) and (min_acceptance >= min_acc_threshold)

        # 7. Primary-only consensus score for before/after comparison
        if canon_primary is not None:
            primary_acceptances = member_satisfaction_plan(cat_records, [canon_primary], category=cat)
            if primary_acceptances:
                if weight_by_vote_weight:
                    prim_weights = [member_weights.get(m, 1.0) for m in sorted(primary_acceptances.keys())]
                    prim_vals = [primary_acceptances[m] for m in sorted(primary_acceptances.keys())]
                    tot_w = sum(prim_weights)
                    prim_mean = sum(w * a for w, a in zip(prim_weights, prim_vals)) / tot_w if tot_w > 0 else (sum(prim_vals) / len(prim_vals))
                else:
                    prim_mean = sum(primary_acceptances.values()) / len(primary_acceptances)
                prim_min = min(primary_acceptances.values())
                prim_raw = (lambda_param * prim_mean) + ((1.0 - lambda_param) * prim_min)
                prim_level = max(0.0, min(1.0, prim_raw - penalty_amount))
            else:
                prim_level = 0.0
        else:
            prim_level = 0.0

        consensus_primary_only = round(prim_level, 4)
        consensus_gain = round(consensus_level - consensus_primary_only, 4)

        # 8. Fairness metrics (Gini and Satisfaction Gap)
        gini_coeff = compute_gini(list(acceptance_dict.values()))
        sat_gap = satisfaction_gap(acceptance_dict)

        # 9. Ties and notes
        is_tie = bool(res.is_tie)
        tied_options = [normalize_name(opt, category=cat) for opt in res.tied_options] if res.tied_options else []
        notes: list[str] = []
        if is_tie:
            notes.append("Choice between tied options is arbitrary.")
        if trivial_single_member:
            notes.append("Trivial decision: single group member.")
        if penalty_amount > 0.0:
            notes.append(
                f"Conflict penalty of {penalty_amount:.2f} deducted due to {unresolved_hard_count} unresolved hard conflicts."
            )

        cat_res = ConsensusCategoryResult(
            category=cat,
            primary_option=canon_primary,
            plan_items=plan_items,
            mean_acceptance=round(mean_acceptance, 4),
            min_acceptance=round(min_acceptance, 4),
            consensus_level=round(consensus_level, 4),
            level_label=level_label,
            consensus_reached=consensus_reached,
            consensus_primary_only=consensus_primary_only,
            consensus_gain=consensus_gain,
            satisfaction_gap=round(sat_gap, 4),
            gini=round(gini_coeff, 4),
            is_tie=is_tie,
            tied_options=sorted(tied_options),
            has_majority=bool(res.has_majority),
            member_acceptance=acceptance_dict,
            trivial_single_member=trivial_single_member,
            conflict_summary=conf_summary,
            notes=notes,
        )
        per_category[cat] = cat_res

    # Overall calculation
    decided_results = list(per_category.values())
    if decided_results:
        overall_level = round(sum(c.consensus_level for c in decided_results) / len(decided_results), 4)
        overall_min_level = round(min(c.consensus_level for c in decided_results), 4)
        if overall_level >= high_threshold:
            overall_label = "high"
        elif overall_level >= medium_threshold:
            overall_label = "medium"
        else:
            overall_label = "low"
        overall_reached = all(c.consensus_reached for c in decided_results)

        # Use the first decided category to populate top-level convenience mirrors
        first_cat = decided_results[0]
        mirror_kwargs = {
            "primary_option": first_cat.primary_option,
            "plan_items": first_cat.plan_items,
            "mean_acceptance": first_cat.mean_acceptance,
            "min_acceptance": first_cat.min_acceptance,
            "consensus_level": first_cat.consensus_level,
            "level_label": first_cat.level_label,
            "consensus_reached": first_cat.consensus_reached,
            "consensus_primary_only": first_cat.consensus_primary_only,
            "consensus_gain": first_cat.consensus_gain,
            "satisfaction_gap": first_cat.satisfaction_gap,
            "gini": first_cat.gini,
            "is_tie": first_cat.is_tie,
            "tied_options": first_cat.tied_options,
            "has_majority": first_cat.has_majority,
            "member_acceptance": first_cat.member_acceptance,
            "trivial_single_member": first_cat.trivial_single_member,
            "conflict_summary": first_cat.conflict_summary,
            "notes": first_cat.notes,
        }
    else:
        overall_level = 0.0
        overall_min_level = 0.0
        overall_label = "low"
        overall_reached = False
        mirror_kwargs = {}

    return ConsensusResult(
        overall_level=overall_level,
        overall_min_level=overall_min_level,
        overall_label=overall_label,
        overall_reached=overall_reached,
        categories_skipped=categories_skipped,
        categories=per_category,
        **mirror_kwargs,
    )


def decide_with_consensus(
    records: list[Any],
    method: str,
    config: dict[str, Any] | None = None,
    conflicts: list[Any] | None = None,
) -> tuple[DecisionResult, ConsensusResult]:
    """Execute decision baseline followed by consensus and fairness metrics computation.

    Does not modify decide().

    Args:
        records: List of preference records.
        method: Decision method ('majority', 'preference_only', 'weighted', 'weighted_minority').
        config: Optional configuration overrides.
        conflicts: Optional list of conflict records.

    Returns:
        tuple of (DecisionResult, ConsensusResult).
    """
    decision_cfg = dict(config or {})
    if conflicts is not None:
        decision_cfg["conflicts"] = conflicts

    # Call existing decide() registry without modifying it
    res = decide(records=records, method=method, config=decision_cfg)

    # Compute consensus outcome
    consensus = compute_consensus(records=records, result=res, config=config, conflicts=conflicts)
    return res, consensus


def to_consensus_decision(
    consensus: ConsensusResult,
    result: DecisionResult | dict[str, DecisionResult] | list[DecisionResult] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Format consensus and decision results for the WANDARAYA Coordinator.

    Output format:
        {
            "options": {category: primary_option},
            "agreement_level": overall_level,
            "level_label": overall_label,
            "consensus_reached": overall_reached,
            "compromise_plan": {category: [ {slot, item, reason} ]},
            "per_category": {...},
            "unresolved": {...},
            (optional "meta": {...})
        }

    Contains structured data only (no raw chat text).

    Args:
        consensus: ConsensusResult instance.
        result: Optional DecisionResult instance or mapping.
        meta: Optional additional metadata dict to pass through.

    Returns:
        Coordinator-compatible JSON-serializable dictionary.
    """
    # 1. Options mapping
    options: dict[str, str | None] = {}
    for cat, cat_res in consensus.categories.items():
        options[cat] = cat_res.primary_option

    # 2. Compromise plan per category
    compromise_plan: dict[str, list[dict[str, Any]]] = {}

    # Extract plans from result if provided
    result_plans: dict[str, list[dict[str, Any]]] = {}
    if result is not None:
        if isinstance(result, DecisionResult):
            if result.plan:
                result_plans[result.category] = result.plan
            elif result.chosen_option:
                result_plans[result.category] = [{"slot": "primary", "item": result.chosen_option, "reason": "winner"}]
        elif isinstance(result, dict):
            for cat, r in result.items():
                if isinstance(r, DecisionResult):
                    if r.plan:
                        result_plans[cat] = r.plan
                    elif r.chosen_option:
                        result_plans[cat] = [{"slot": "primary", "item": r.chosen_option, "reason": "winner"}]
        elif isinstance(result, list):
            for r in result:
                if isinstance(r, DecisionResult):
                    if r.plan:
                        result_plans[r.category] = r.plan
                    elif r.chosen_option:
                        result_plans[r.category] = [{"slot": "primary", "item": r.chosen_option, "reason": "winner"}]

    for cat, cat_res in consensus.categories.items():
        if cat in result_plans:
            compromise_plan[cat] = result_plans[cat]
        elif cat_res.plan_items:
            compromise_plan[cat] = [
                {"slot": f"slot_{i+1}", "item": item, "reason": "plan_item"}
                for i, item in enumerate(cat_res.plan_items)
            ]
        else:
            compromise_plan[cat] = []

    # 3. Per-category detailed metrics
    per_category_dict: dict[str, Any] = {}
    for cat, cat_res in consensus.categories.items():
        per_category_dict[cat] = cat_res.model_dump()

    # 4. Unresolved conflicts and rejections
    unresolved_dict: dict[str, Any] = {}
    for cat, cat_res in consensus.categories.items():
        unresolved_dict[cat] = cat_res.conflict_summary

    output: dict[str, Any] = {
        "options": options,
        "agreement_level": consensus.overall_level,
        "level_label": consensus.overall_label,
        "consensus_reached": consensus.overall_reached,
        "compromise_plan": compromise_plan,
        "per_category": per_category_dict,
        "unresolved": unresolved_dict,
    }

    # Pass through optional meta dictionary if present
    effective_meta: dict[str, Any] = {}
    if meta:
        effective_meta.update(meta)

    # Check for future metadata on result (such as budget_override flag)
    if result is not None:
        if hasattr(result, "meta") and isinstance(result.meta, dict):
            effective_meta.update(result.meta)
        for flag in ["budget_override", "override_applied", "budget_status"]:
            if hasattr(result, flag):
                effective_meta[flag] = getattr(result, flag)

    if effective_meta:
        output["meta"] = effective_meta

    return output
