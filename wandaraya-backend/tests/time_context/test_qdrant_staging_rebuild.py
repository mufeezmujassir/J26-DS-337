import math

import pytest

from scripts.rebuild_qdrant_staging import (
    STAGING_COLLECTION_PREFIX,
    canonical_hash,
    payload_for,
    require_staging_collection,
    validate_vector,
)
from scripts.validate_qdrant_staging import full_scroll_ids


class Document:
    attraction_id = 99
    name = "Example"
    city = "Galle"
    district = "Galle"
    province = "Southern"
    categories = ["Heritage"]
    activities = ["Photography"]


def test_rejects_the_production_collection_name():
    with pytest.raises(ValueError, match="non-staging"):
        require_staging_collection("sri_lanka_attractions")


def test_accepts_only_the_staging_prefix():
    require_staging_collection(STAGING_COLLECTION_PREFIX)
    require_staging_collection(STAGING_COLLECTION_PREFIX + "_20261018")


def test_vector_validation_requires_normalized_bge_dimension():
    vector = [1 / math.sqrt(1024)] * 1024
    assert validate_vector(vector)["valid"] is True
    assert "unexpected_dimension" in validate_vector([1.0])["reasons"]
    assert "non_finite_value" in validate_vector([float("nan")] * 1024)["reasons"]


def test_payload_uses_stable_postgresql_point_identity_and_hash():
    payload = payload_for(Document(), "hash")
    assert payload["attraction_id"] == 99
    assert payload["semantic_document_sha256"] == "hash"
    assert payload["embedding_model"] == "BAAI/bge-large-en-v1.5"


def test_scope_hash_is_deterministic():
    assert canonical_hash([1, 2, 3]) == canonical_hash([1, 2, 3])


def test_full_scroll_ids_reports_an_error_without_hiding_partial_progress():
    class BrokenClient:
        def scroll(self, **_kwargs):
            raise RuntimeError("broken scroll")

    ids, error = full_scroll_ids(BrokenClient(), "sri_lanka_attractions_staging")
    assert ids == set()
    assert "broken scroll" in error
