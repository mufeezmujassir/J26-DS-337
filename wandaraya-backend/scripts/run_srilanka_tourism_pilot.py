"""Validate or explicitly execute a bounded Sri Lanka Tourism pilot."""
from __future__ import annotations
import argparse, asyncio, json
from pathlib import Path
from app.time_context.governance.homepage_discovery import extract_and_discover_homepage, write_gate4_review_artifacts
from app.time_context.governance.live_pilot import ControlledSriLankaTourismFetcher, LivePilotSettings, build_dry_run, load_source_authorization_configuration

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    args = parser.parse_args()
    config = load_source_authorization_configuration(Path(args.config))
    settings = LivePilotSettings()
    if not args.execute:
        print(json.dumps({"mode":"dry_run","errors":config.readiness_errors(settings),"url_plan":[item.model_dump() for item in build_dry_run(config.exact_urls, config.permission, settings)]}, indent=2, default=str)); return
    if not args.confirm_execute: parser.error("--execute requires --confirm-execute")
    results = asyncio.run(ControlledSriLankaTourismFetcher(config, settings).fetch_exact_urls(execute=True))
    artifact_paths = []
    for item in results:
        if item.source_url == "https://srilanka.travel/" and item.raw_content is not None:
            discovery = extract_and_discover_homepage(source_url=item.source_url, html=item.raw_content)
            pilot, inventory = write_gate4_review_artifacts(
                result=discovery,
                pilot_metadata=item.model_dump(),
                reports_dir=Path("data/reports"),
            )
            artifact_paths.extend([str(pilot), str(inventory)])
    print(json.dumps({"mode":"live_pilot","staged_records":[item.model_dump() for item in results], "review_artifacts": artifact_paths}, indent=2, default=str))
if __name__ == "__main__": main()
