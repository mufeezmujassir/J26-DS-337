"""Authorization-bound NASA POWER acquisition for a prepared Batch 02 manifest.

The default is a completely offline manifest validation.  Network acquisition is
deliberately unreachable unless both explicit execution flags are supplied.  This
script never opens a database session and never persists climate observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.climate.providers.nasa_power import NasaPowerRequest, fetch, normalize
from app.climate.validation import validate_daily_records


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_new_or_identical(path: Path, data: bytes) -> str:
    """Make reruns idempotent but refuse to replace a different artifact."""
    digest = _sha256(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = _sha256(path.read_bytes())
        if existing != digest:
            raise RuntimeError(f"refusing checksum-changing overwrite: {path}")
        return digest
    path.write_bytes(data)
    return digest


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("manifest must contain one or more samples")
    for sample in samples:
        required = {"sample_id", "latitude", "longitude", "expected_records", "raw_file", "processed_file"}
        missing = sorted(required.difference(sample))
        if missing:
            raise ValueError(f"invalid Batch 02 sample: missing {', '.join(missing)}")
        if sample["expected_records"] != 5844:
            raise ValueError(f"unexpected expected_records for {sample['sample_id']}")
    return manifest


def dry_run_result(manifest: dict) -> dict:
    return {
        "status": "DRY_RUN_VALID",
        "samples": len(manifest["samples"]),
        "expected_records": sum(item["expected_records"] for item in manifest["samples"]),
        "network_requests": 0,
        "postgresql_writes": False,
        "qdrant_writes": False,
    }


def request_from_manifest_url(url: str) -> NasaPowerRequest:
    """Reconstruct the typed request and reject altered/non-POWER URLs."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "power.larc.nasa.gov":
        raise ValueError("manifest request URL is not the NASA POWER HTTPS endpoint")
    query = parse_qs(parsed.query)
    try:
        return NasaPowerRequest(
            latitude=float(query["latitude"][0]),
            longitude=float(query["longitude"][0]),
            start=datetime.strptime(query["start"][0], "%Y%m%d").date(),
            end=datetime.strptime(query["end"][0], "%Y%m%d").date(),
            time_standard=query.get("time-standard", ["UTC"])[0],
        )
    except (KeyError, ValueError, IndexError) as exc:
        raise ValueError("manifest has an invalid NASA POWER request URL") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute-acquisition", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    args = parser.parse_args()

    if args.execute_acquisition == args.dry_run:
        raise SystemExit("choose exactly one of --dry-run or --execute-acquisition")
    if args.execute_acquisition and not args.confirm_execute:
        raise SystemExit("--execute-acquisition requires --confirm-execute")

    manifest = load_manifest(args.manifest)
    if args.dry_run:
        print(json.dumps(dry_run_result(manifest), indent=2))
        return

    results: list[dict] = []
    for sample in manifest["samples"]:
        request = request_from_manifest_url(sample["request_url"])
        raw_path = Path(sample["raw_file"])
        processed_path = Path(sample["processed_file"])
        try:
            if raw_path.exists():
                raw = raw_path.read_bytes()
                payload = json.loads(raw)
                source = "reused_identical_raw_artifact"
            else:
                payload, raw = fetch(request)
                source = "network"
            records, metadata = normalize(payload)
            validation = validate_daily_records(records, expected_records=sample["expected_records"])
            if validation["accepted"] != sample["expected_records"]:
                raise ValueError(f"unexpected accepted record count: {validation['accepted']}")
            checksum = _write_new_or_identical(raw_path, raw)
            processed = json.dumps(
                {"sample": sample, "records": records, "metadata": metadata},
                sort_keys=True,
                indent=2,
                default=str,
            ).encode("utf-8")
            _write_new_or_identical(processed_path, processed)
            results.append({"sample_id": sample["sample_id"], "status": "VALIDATED", "source": source, "checksum_sha256": checksum, "validation": validation})
        except Exception as exc:
            results.append({"sample_id": sample["sample_id"], "status": "FAILED", "error": str(exc)})
            break

    summary = {
        "status": "ACQUISITION_COMPLETED_NO_DATABASE_PERSISTENCE" if all(x["status"] == "VALIDATED" for x in results) else "ACQUISITION_FAILED",
        "results": results,
        "postgresql_writes": False,
        "qdrant_writes": False,
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
