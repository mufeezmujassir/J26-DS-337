import argparse
import asyncio

import pytest

from scripts.run_srilanka_tourism_google_places_gate5d import run


def test_existing_batch_report_blocks_before_queue_or_network_access(tmp_path):
    (tmp_path / "stage_10_1_3e_gate5d_repeat_google_places_discovery_summary.json").write_text("{}")
    args = argparse.Namespace(
        live=True, execute=True, confirm_execute=True, max_records=5,
        reports_dir=str(tmp_path), batch_id="repeat", queue=str(tmp_path / "not-read.json"),
        offset=0, resume_manifest=None, max_candidates=5,
        request_interval_seconds=0, max_retries=0, include_details=True,
    )
    with pytest.raises(FileExistsError, match="no request was made"):
        asyncio.run(run(args))
