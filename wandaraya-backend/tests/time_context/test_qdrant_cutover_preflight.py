from scripts.preflight_qdrant_production_cutover import validate_plan


def plan():
    return {
        "status": "READY_FOR_HUMAN_CUTOVER_REVIEW",
        "blockers": [],
        "validated_staging": {
            "collection": "sri_lanka_attractions_staging",
            "point_count": 6120,
            "embedding_model": "BAAI/bge-large-en-v1.5",
            "vector_dimension": 1024,
            "rebuild_report_sha256": "rebuild",
            "validation_report_sha256": "validation",
            "staging_snapshot": {"name": "valid.snapshot", "checksum": "a" * 64},
        },
    }


def test_valid_review_plan_passes_read_only_preflight():
    assert validate_plan(plan(), "rebuild", "validation") == []


def test_changed_report_hash_blocks_preflight():
    assert "rebuild_report_hash_mismatch" in validate_plan(plan(), "changed", "validation")


def test_wrong_collection_blocks_preflight():
    item = plan()
    item["validated_staging"]["collection"] = "sri_lanka_attractions"
    assert "unexpected_replacement_collection" in validate_plan(item, "rebuild", "validation")
