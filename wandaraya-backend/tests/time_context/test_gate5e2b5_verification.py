from __future__ import annotations

import asyncio
from hashlib import sha256

import pytest

from scripts.run_srilanka_tourism_gate5e2b5 import _v5_proposals, assess_candidates, execute_verification


class FakeClient:
    def __init__(self): self.searches = 0; self.details = 0
    async def text_search(self, *, query, max_results):
        self.searches += 1
        return [{"id": "place-1", "displayName": {"text": "Delft Dutch Fort"}, "primaryType": "tourist_attraction", "types": ["tourist_attraction"]}]
    async def get_place_details(self, place_id):
        self.details += 1
        return {"id": place_id}


def record(source_id: str = "source:1"):
    return {"source_attraction_id": source_id, "official_name": "Delft Dutch Fort", "queries": ["Delft Dutch Fort"], "max_api_requests": 2}


def checkpoint(queue_path):
    return {"version": 1, "queue_sha256": sha256(queue_path.read_bytes()).hexdigest(), "completed_source_ids": [], "failed_source_ids": [], "results": [], "cumulative_requests": 0}


def test_offline_mode_makes_no_requests(tmp_path):
    queue = [record()]
    path = tmp_path / "queue.json"; path.write_text('{"records": []}')
    cp = checkpoint(path); fake = FakeClient()
    result = asyncio.run(execute_verification(queue=queue, checkpoint=cp, checkpoint_path=tmp_path / "checkpoint.json", live=False, max_requests=60, max_records=5, client=fake))
    assert fake.searches == 0
    assert result["completed_source_ids"] == []


def test_resume_skips_completed_and_checkpoints(tmp_path):
    path = tmp_path / "queue.json"; path.write_text('{"records": []}')
    cp = checkpoint(path); fake = FakeClient()
    result = asyncio.run(execute_verification(queue=[record("source:1"), record("source:2")], checkpoint=cp, checkpoint_path=tmp_path / "checkpoint.json", live=True, max_requests=60, max_records=1, client=fake))
    assert result["completed_source_ids"] == ["source:1"]
    result = asyncio.run(execute_verification(queue=[record("source:1"), record("source:2")], checkpoint=result, checkpoint_path=tmp_path / "checkpoint.json", live=True, max_requests=60, max_records=1, client=fake))
    assert result["completed_source_ids"] == ["source:1", "source:2"]
    assert fake.searches == 2


def test_locality_candidate_is_not_an_attraction_identity():
    assessment = assess_candidates(record(), [{"id": "locality", "displayName": {"text": "Delft"}, "primaryType": "locality", "types": ["locality", "political"]}])
    assert assessment["assessment"] == "RELATED_LOCALITY_NOT_ATTRACTION"


def test_budget_prevents_second_request_when_only_one_is_allowed(tmp_path):
    path = tmp_path / "queue.json"; path.write_text('{"records": []}')
    fake = FakeClient()
    result = asyncio.run(execute_verification(queue=[record()], checkpoint=checkpoint(path), checkpoint_path=tmp_path / "checkpoint.json", live=True, max_requests=1, max_records=1, client=fake))
    assert result["cumulative_requests"] == 1
    assert fake.details == 0


def test_v5_preserves_non_targeted_insert_and_link_actions(tmp_path):
    v4 = tmp_path / "v4.json"
    v4.write_text('{"records": [{"source_attraction_id": "source:1", "corrected_proposed_action": "INSERT_NEW_CANDIDATE"}, {"source_attraction_id": "source:2", "corrected_proposed_action": "LINK_SOURCE_REFERENCE_CANDIDATE"}]}')
    output = _v5_proposals(v4, [])
    assert [item["corrected_proposed_action"] for item in output] == ["INSERT_NEW_CANDIDATE", "LINK_SOURCE_REFERENCE_CANDIDATE"]

