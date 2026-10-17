import json
from pathlib import Path

from app.time_context.governance.google_places_reconciliation import consolidate_manifests


def test_prior_checkpoint_results_are_preserved_when_a_new_live_batch_is_added():
    queue = [{"external_source_id": "official:1"}, {"external_source_id": "official:2"}]
    prior_as_live = {"mode": "live", "results": [{"external_source_id": "official:1", "classification": "new_google_place_candidate", "candidates": []}]}
    new_live = {"mode": "live", "results": [{"external_source_id": "official:2", "classification": "new_google_place_candidate", "candidates": []}]}
    result = consolidate_manifests(queue=queue, manifests=[prior_as_live, new_live])
    assert result["completed_records"] == ["official:1", "official:2"]
