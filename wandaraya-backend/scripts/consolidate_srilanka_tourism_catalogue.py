"""Consolidate one or more saved catalogue HTML captures without network access."""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from app.time_context.governance.catalogue_discovery import extract_catalogue_page, write_catalogue_reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-manifest", action="append")
    parser.add_argument("--capture-root", help="Use every saved capture_manifest.json below this review-only directory.")
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args()
    if not args.capture_manifest and not args.capture_root:
        parser.error("provide --capture-manifest at least once or --capture-root")
    manifest_names = list(args.capture_manifest or [])
    if args.capture_root:
        # Catalogue batches are intentionally named catalogue_* so attraction
        # detail fixtures cannot contaminate catalogue-card consolidation.
        manifest_names.extend(str(path) for path in sorted(Path(args.capture_root).glob("catalogue_*/capture_manifest.json")))
    if not manifest_names:
        parser.error("no capture manifests were found")
    pages = []
    for manifest_name in sorted(set(manifest_names)):
        manifest_path = Path(manifest_name)
        if not manifest_path.is_file():
            parser.error(
                f"capture manifest was not found: {manifest_path}. It is created only after a successful "
                "approved catalogue batch executes; do not run consolidation before that step."
            )
        capture = json.loads(manifest_path.read_text(encoding="utf-8"))
        for artifact in capture.get("artifacts", []):
            content = (manifest_path.parent / artifact["file"]).read_bytes()
            if sha256(content).hexdigest() != artifact["content_sha256"]:
                raise ValueError(f"fixture checksum mismatch: {manifest_path.parent / artifact['file']}")
            pages.append(extract_catalogue_page(html=content, source_url=artifact["source_url"], retrieved_at=datetime.fromisoformat(artifact["retrieved_at"])))
    reports = write_catalogue_reports(pages=pages, reports_dir=Path("data/reports"), batch_id=args.batch_id)
    print(json.dumps({"mode": "offline_catalogue_consolidation", "network_requests": 0, "reports": {key: str(value) for key, value in reports.items()}}, indent=2))


if __name__ == "__main__":
    main()
