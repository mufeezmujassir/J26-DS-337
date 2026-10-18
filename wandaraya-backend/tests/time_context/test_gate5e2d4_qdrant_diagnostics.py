import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.sync_srilanka_tourism_gate5e2d4 import (
    SNAPSHOT_CHECKSUM,
    SNAPSHOT_NAME,
    bounded_identity_scan,
    client_filtered_scroll,
    infer_schema,
    scroll_body,
    snapshot_validation,
)


class Point:
    def __init__(self, payload, point_id=1):
        self.payload = payload
        self.id = point_id


def test_filter_body_uses_qdrant_rest_filter_shape():
    assert scroll_body(field="attraction_id", value=1)["filter"] == {
        "must": [{"key": "attraction_id", "match": {"value": 1}}]
    }


def test_unfiltered_body_does_not_send_an_empty_filter():
    assert "filter" not in scroll_body()


def test_schema_audit_confirms_actual_identity_fields():
    audit = infer_schema([Point({"attraction_id": 1, "name": "Galle Fort", "district": "Galle"})])
    assert audit["confirmed_identity_fields"]["attraction_id"] is True
    assert audit["confirmed_identity_fields"]["google_place_id"] is False
    assert audit["fields"]["attraction_id"] == ["int"]


def test_snapshot_constants_are_integrity_values_not_placeholders():
    assert SNAPSHOT_NAME.endswith(".snapshot")
    assert len(SNAPSHOT_CHECKSUM) == 64


class WorkingClient:
    def scroll(self, **kwargs):
        return [], None


class FailingClient:
    def scroll(self, **kwargs):
        raise RuntimeError("server returned 500")


def test_python_client_filter_reports_empty_valid_result():
    result = client_filtered_scroll(WorkingClient(), "collection", "attraction_id", 1)
    assert result["status"] == "ok"
    assert result["returned_points"] == 0


def test_python_client_filter_preserves_server_errors():
    result = client_filtered_scroll(FailingClient(), "collection", "attraction_id", 1)
    assert result["status"] == "failed"
    assert result["error_type"] == "RuntimeError"


class OnePageThenFailureClient:
    def __init__(self):
        self.calls = 0

    def scroll(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return [Point({"attraction_id": 1})], 2
        raise RuntimeError("OffsetZero")


def test_bounded_scan_reports_partial_pagination_failure_without_throwing():
    result = bounded_identity_scan(
        OnePageThenFailureClient(), "collection",
        [{"attraction_id": 6604, "google_place_id": None}], page_size=1,
    )
    assert result["status"] == "failed"
    assert result["points_seen"] == 1
    assert result["pagination_error"]["error_type"] == "RuntimeError"


def test_snapshot_list_is_not_treated_as_persistent_storage_proof():
    response = {"status": "ok", "response_body": {"result": [{
        "name": SNAPSHOT_NAME, "size": 1, "checksum": SNAPSHOT_CHECKSUM,
    }]}}
    with tempfile.TemporaryDirectory() as directory, patch(
        "scripts.sync_srilanka_tourism_gate5e2d4.rest_request", return_value=response
    ):
        report = snapshot_validation("http://qdrant:6333", Path(directory) / "missing.json")
    assert report["accessible_via_qdrant_api"] is True
    assert report["persistent_storage_verified"] is False
    assert report["ready_for_write"] is False
