from scripts.prepare_qdrant_production_cutover import validate_evidence


def valid_reports():
    rebuild = {
        "status": "STAGING_REBUILD_COMPLETED", "failures": [],
        "collection": "sri_lanka_attractions_staging",
        "embedding_model": "BAAI/bge-large-en-v1.5", "vector_dimension": 1024,
        "postgresql_active_attractions": 2,
    }
    validation = {
        "status": "STAGING_VALIDATED", "collection": "sri_lanka_attractions_staging",
        "expected_postgresql_active_attractions": 2,
        "checks": {name: {"status": "ok"} for name in (
            "collection", "direct_retrieve", "filtered_scroll_existing", "filtered_scroll_absent",
            "full_unfiltered_scroll", "vector_dimension", "vector_search",
        )},
    }
    validation["checks"]["collection"]["points_count"] = 2
    validation["checks"]["full_unfiltered_scroll"]["unique_point_ids"] = 2
    return rebuild, validation


def test_validated_evidence_has_no_cutover_plan_blocker():
    rebuild, validation = valid_reports()
    assert validate_evidence(rebuild, validation) == []


def test_count_mismatch_blocks_cutover_plan():
    rebuild, validation = valid_reports()
    validation["checks"]["collection"]["points_count"] = 1
    assert "staging_scope_count_mismatch" in validate_evidence(rebuild, validation)


def test_failed_filter_validation_blocks_cutover_plan():
    rebuild, validation = valid_reports()
    validation["checks"]["filtered_scroll_existing"]["status"] = "failed"
    assert "staging_read_validation_incomplete" in validate_evidence(rebuild, validation)
