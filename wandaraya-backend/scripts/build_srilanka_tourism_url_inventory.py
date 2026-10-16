"""Build Gate 5A review artifacts from saved Gate 4 reports; no network access."""
from __future__ import annotations

import json
from pathlib import Path

from app.time_context.governance.url_intelligence import build_gate5a_reports


def main() -> None:
    reports = Path("data/reports")
    output = build_gate5a_reports(
        gate4_pilot_path=reports / "stage_10_1_3d_gate4_pilot.json",
        gate4_urls_path=reports / "stage_10_1_3d_gate4_discovered_urls.json",
        output_dir=reports,
    )
    print(json.dumps({"mode": "offline_review_only", "reports": {name: str(path) for name, path in output.items()}}, indent=2))


if __name__ == "__main__":
    main()
