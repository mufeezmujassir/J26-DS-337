"""Read-only validation and presentation of best-time advisory reports.

Advisories are explanations only.  They never participate in opening-hours
evaluation or ranking, and this module never invokes an LLM.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DuplicateJsonKeyError(ValueError):
    """Raised instead of silently accepting ambiguous JSON evidence."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_strict_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    if not isinstance(value, dict):
        raise ValueError("advisory report must be a JSON object")
    return value


def unavailable_advisory(reason: str) -> dict[str, Any]:
    return {
        "text": None,
        "evidence_tier": "advisory_unavailable",
        "model_reported_confidence": None,
        "evidence_confidence": "unavailable",
        "source_verification_status": "unavailable",
        "cited_sources": [],
        "limitations": [reason],
        "generated_at": None,
    }


def normalise_advisory_report(report: dict[str, Any], attraction_id: int) -> dict[str, Any]:
    """Return a client-safe advisory or an explicit unavailable state.

    A cited URL can prove source association, not that an LLM's wording is an
    independently verified factual claim.  That distinction is surfaced in
    ``source_verification_status`` and ``evidence_confidence``.
    """
    if report.get("attraction_id") != attraction_id:
        return unavailable_advisory("advisory_report_attraction_id_mismatch")
    status = report.get("status")
    advisory = report.get("llm_advisory")
    if status not in {"SOURCE_SUPPORTED_ADVISORY_AVAILABLE", "LLM_GENERATED_ADVISORY_AVAILABLE"}:
        return unavailable_advisory(f"advisory_report_status_{status or 'missing'}")
    if not isinstance(advisory, dict) or not isinstance(advisory.get("best_time_advisory"), str):
        return unavailable_advisory("advisory_text_missing")

    source_urls = {
        item.get("source_url") for item in report.get("source_excerpts", [])
        if isinstance(item, dict) and isinstance(item.get("source_url"), str)
    }
    cited_sources = advisory.get("cited_source_urls") or []
    if not isinstance(cited_sources, list) or not all(isinstance(url, str) for url in cited_sources):
        return unavailable_advisory("advisory_citations_invalid")
    model_confidence = advisory.get("confidence")
    if not isinstance(model_confidence, (int, float)) or isinstance(model_confidence, bool) or not 0 <= model_confidence <= 1:
        model_confidence = None

    if status == "SOURCE_SUPPORTED_ADVISORY_AVAILABLE":
        if not cited_sources or not set(cited_sources).issubset(source_urls):
            return unavailable_advisory("source_supported_advisory_citation_not_associated")
        return {
            "text": advisory["best_time_advisory"],
            "evidence_tier": "source_supported_advisory",
            "model_reported_confidence": model_confidence,
            "evidence_confidence": "low",
            "source_verification_status": "cited_sources_associated_with_stored_descriptions_claim_not_independently_verified",
            "cited_sources": cited_sources,
            "limitations": [*report.get("limitations", []), advisory.get("limitations", "LLM wording is advisory only.")],
            "generated_at": report.get("generated_at_utc"),
        }

    # LLM-only reports must carry no claimed source attribution.
    if source_urls or cited_sources:
        return unavailable_advisory("llm_generated_advisory_contains_unverified_source_claim")
    return {
        "text": advisory["best_time_advisory"],
        "evidence_tier": "llm_generated_advisory",
        "model_reported_confidence": model_confidence,
        "evidence_confidence": "low",
        "source_verification_status": "model_generated_without_source_evidence",
        "cited_sources": [],
        "limitations": [*report.get("limitations", []), advisory.get("limitations", "Model-generated guidance.")],
        "generated_at": report.get("generated_at_utc"),
    }


def load_advisory_for_attraction(attraction_id: int, report_root: Path = Path("data/reports")) -> dict[str, Any]:
    path = report_root / f"stage12_2_llm_best_time_advisory_{attraction_id}.json"
    if not path.exists():
        return unavailable_advisory("no_saved_advisory_report")
    try:
        return normalise_advisory_report(load_strict_json(path), attraction_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return unavailable_advisory(f"invalid_advisory_report:{exc}")
