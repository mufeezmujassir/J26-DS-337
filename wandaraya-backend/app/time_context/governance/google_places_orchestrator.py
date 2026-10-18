"""Pure checkpoint planning for resumable, bounded Gate 5D batches."""
from __future__ import annotations
import json
import os
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any
from app.time_context.governance.google_places_reconciliation import consolidate_manifests

def queue_sha(path: Path) -> str: return sha256(path.read_bytes()).hexdigest()

def discover_live_manifests(reports_dir: Path) -> list[Path]:
    return sorted(path for path in reports_dir.glob("stage_10_1_3e_gate5d_*_google_places_full_enrichment_manifest.json")
                  if json.loads(path.read_text(encoding="utf-8")).get("mode") == "live")

def checkpoint(*, queue_path: Path, manifest_paths: list[Path], batch_size: int = 5) -> dict[str, Any]:
    if not 1 <= batch_size <= 5: raise ValueError("batch_size must be between 1 and 5")
    queue = json.loads(queue_path.read_text(encoding="utf-8")).get("records", [])
    manifests=[]; usage=Counter()
    for path in manifest_paths:
        if not path.is_file(): raise FileNotFoundError(f"manifest not found: {path}")
        item=json.loads(path.read_text(encoding="utf-8"))
        if item.get("mode") != "live": raise ValueError(f"non-live manifest cannot be a completed checkpoint: {path}")
        summary=path.with_name(path.name.replace("full_enrichment_manifest", "discovery_summary"))
        if not summary.is_file(): raise ValueError(f"missing discovery summary for {path}")
        expected=json.loads(summary.read_text(encoding="utf-8")).get("queue_sha256")
        if expected != queue_sha(queue_path): raise ValueError(f"queue SHA-256 mismatch for {path}")
        manifests.append(item)
        api=path.with_name(path.name.replace("full_enrichment_manifest", "api_usage_summary"))
        if api.is_file(): usage.update({k:int(v) for k,v in json.loads(api.read_text(encoding="utf-8")).items() if k in {"network_requests","search_requests","details_requests"} and isinstance(v,int)})
    merged=consolidate_manifests(queue=queue, manifests=manifests)
    classifications=Counter(item.get("classification") for item in merged["results"])
    suspicious=[item for item in merged["results"] if item.get("classification") in {"ambiguous_multiple_candidates","related_locality_not_attraction","high_confidence_candidate_review"} or any(candidate.get("location_conflict") for candidate in item.get("candidates",[]))]
    pending=[item for item in queue if str(item.get("external_source_id")) in set(merged["remaining_records"])]
    planned=[pending[i:i+batch_size] for i in range(0,len(pending),batch_size)]
    return {"mode":"checkpoint", "queue_path":str(queue_path), "queue_sha256":queue_sha(queue_path), "source_manifests":[str(p) for p in manifest_paths],
      "results":merged["results"], "completed_records":merged["completed_records"], "remaining_records":merged["remaining_records"], "retriable_records":merged["retriable_records"],
      "duplicate_google_place_clusters":merged["duplicate_google_place_clusters"], "progress":{"total":len(queue),"completed":len(merged["completed_records"]),"remaining":len(merged["remaining_records"]),"failed":len(merged["retriable_records"]),"retriable":len(merged["retriable_records"]),"api_requests":dict(usage),"classifications":dict(sorted(classifications.items()))},
      "suspicious_matches":suspicious,"planned_batches":[[str(x.get("external_source_id")) for x in batch] for batch in planned],"postgresql_writes":False,"qdrant_writes":False,"network_requests":0}

def write_checkpoint(value: dict[str,Any], path: Path)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value,indent=2,sort_keys=True),encoding="utf-8")
    os.replace(temporary, path)
