import json

from app.recommendation.time_context.advisory import (
    DuplicateJsonKeyError,
    load_strict_json,
    normalise_advisory_report,
)


def source_report():
    return {
        "attraction_id": 1,
        "status": "SOURCE_SUPPORTED_ADVISORY_AVAILABLE",
        "source_excerpts": [{"source_url": "https://example.test/galle"}],
        "limitations": ["Not opening-hours evidence."],
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "llm_advisory": {"best_time_advisory": "Visit in the morning.", "confidence": 0.9, "cited_source_urls": ["https://example.test/galle"], "limitations": "Advice only."},
    }


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"attraction_id": 1, "attraction_id": 2}', encoding="utf-8")
    try:
        load_strict_json(path)
    except DuplicateJsonKeyError:
        pass
    else:
        raise AssertionError("duplicate JSON key was accepted")


def test_source_supported_advisory_has_separate_confidence_semantics():
    result = normalise_advisory_report(source_report(), 1)
    assert result["evidence_tier"] == "source_supported_advisory"
    assert result["model_reported_confidence"] == 0.9
    assert result["evidence_confidence"] == "low"
    assert "claim_not_independently_verified" in result["source_verification_status"]


def test_unassociated_citation_is_rejected():
    report = source_report()
    report["llm_advisory"]["cited_source_urls"] = ["https://untrusted.test/page"]
    assert normalise_advisory_report(report, 1)["evidence_tier"] == "advisory_unavailable"


def test_llm_only_advisory_cannot_claim_sources():
    report = source_report()
    report["status"] = "LLM_GENERATED_ADVISORY_AVAILABLE"
    report["source_excerpts"] = []
    report["llm_advisory"]["cited_source_urls"] = ["https://example.test/galle"]
    assert normalise_advisory_report(report, 1)["evidence_tier"] == "advisory_unavailable"


def test_missing_advisory_is_explicitly_unavailable():
    report = {"attraction_id": 1, "status": "DRY_RUN_NO_GROQ_REQUEST"}
    result = normalise_advisory_report(report, 1)
    assert result["text"] is None
    assert result["evidence_tier"] == "advisory_unavailable"


def test_advisory_does_not_supply_opening_status_or_rank_score_fields():
    result = normalise_advisory_report(source_report(), 1)
    assert "opening_status" not in result
    assert "ranking_score" not in result


