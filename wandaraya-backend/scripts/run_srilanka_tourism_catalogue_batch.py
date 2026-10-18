"""Validate or execute one bounded approved Gate 5B.2 catalogue batch."""
from __future__ import annotations

import argparse
import asyncio
import json
from hashlib import sha256
from pathlib import Path

from app.time_context.governance.catalogue_discovery import CatalogueBatchPlan, extract_catalogue_page, write_catalogue_reports
from app.time_context.governance.live_pilot import ControlledSriLankaTourismFetcher, LivePilotSettings, load_source_authorization_configuration
from app.time_context.governance.multi_page_pilot import capture_batch_directory, write_captured_html_fixtures


def _allowed_urls(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = ("known_distinct_url_structures", "candidates")
    urls = {item["canonical_url"] for group in groups for item in data.get(group, []) if isinstance(item, dict) and isinstance(item.get("canonical_url"), str)}
    return urls | {url for url in data.get("remaining_urls", []) if isinstance(url, str)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-config", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--catalogue-manifest", default="data/reports/stage_10_1_3e_gate5b2_catalogue_seed_manifest.json")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--capture-root", default="data/review/srilanka_tourism")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    args = parser.parse_args()
    plan_path = Path(args.plan)
    if not plan_path.is_file():
        parser.error(
            f"catalogue plan was not found: {plan_path}. In Windows CMD create it with: "
            "copy /Y config\\srilanka_tourism_gate5b2_catalogue_plan.example.json "
            "config\\srilanka_tourism_gate5b2_catalogue_plan.local.json"
        )
    catalogue_manifest_path = Path(args.catalogue_manifest)
    if not catalogue_manifest_path.is_file():
        parser.error(
            f"catalogue manifest was not found: {catalogue_manifest_path}. Run: "
            "docker exec -it wandaraya-api python -m scripts.build_srilanka_tourism_catalogue_manifest"
        )
    authorization = load_source_authorization_configuration(Path(args.authorization_config))
    plan = CatalogueBatchPlan.model_validate(json.loads(plan_path.read_text(encoding="utf-8")))
    settings = LivePilotSettings(emergency_stop=plan.emergency_stop)
    errors = plan.readiness_errors(_allowed_urls(catalogue_manifest_path), settings.max_pages)
    if plan.source_manifest_sha256 and sha256(catalogue_manifest_path.read_bytes()).hexdigest() != plan.source_manifest_sha256:
        errors.append("source_manifest_checksum_mismatch")
    errors += authorization.readiness_errors(settings)
    missing_allowlist = sorted(set(plan.exact_urls) - set(authorization.exact_urls))
    errors += [f"exact_url_not_in_authorization_config:{url}" for url in missing_allowlist]
    if not args.execute:
        print(json.dumps({"mode": "offline_batch_validation", "network_requests": 0, "errors": sorted(set(errors)), "approved_urls": [item.model_dump() for item in plan.approved_urls]}, indent=2))
        return
    if not args.confirm_execute:
        parser.error("--execute requires --confirm-execute")
    if errors:
        raise PermissionError("Gate 5B.2 acquisition blocked: " + ", ".join(sorted(set(errors))))
    capture_root = Path(args.capture_root)
    if capture_batch_directory(capture_root=capture_root, batch_id=args.batch_id).exists():
        raise FileExistsError(f"capture batch already exists: {capture_batch_directory(capture_root=capture_root, batch_id=args.batch_id)}")
    effective = authorization.model_copy(update={"exact_urls": [item.canonical_url for item in plan.approved_urls]})
    fetched = asyncio.run(ControlledSriLankaTourismFetcher(effective, settings).fetch_exact_urls(execute=True))
    capture_path = write_captured_html_fixtures(fetched=fetched, capture_root=capture_root, batch_id=args.batch_id)
    pages = [extract_catalogue_page(html=item.raw_content or b"", source_url=item.source_url, retrieved_at=item.retrieved_at) for item in fetched]
    reports = write_catalogue_reports(pages=pages, reports_dir=Path("data/reports"), batch_id=args.batch_id)
    print(json.dumps({"mode": "gate5b2_live_catalogue_batch", "capture_manifest": str(capture_path), "reports": {key: str(value) for key, value in reports.items()}, "postgresql_writes": False, "qdrant_writes": False}, indent=2))


if __name__ == "__main__":
    main()
