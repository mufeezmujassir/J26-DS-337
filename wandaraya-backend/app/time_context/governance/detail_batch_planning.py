"""Offline planning for all attraction-detail URLs already observed in a listing."""
from __future__ import annotations

import json
from pathlib import Path

from app.time_context.governance.url_intelligence import canonicalize_tourism_url, extract_external_source_id


def build_detail_manifest_from_listing(extraction_path: Path) -> dict:
    """Use only captured listing references; never guess pagination/detail URLs."""
    payload = json.loads(extraction_path.read_text(encoding="utf-8"))
    candidates: list[dict] = []
    seen: set[str] = set()
    for record in payload.get("records", []):
        if record.get("source_page_category") != "attraction_listing":
            continue
        for reference in record.get("extracted_fields", {}).get("referenced_attractions", []):
            source_url = reference.get("source_url")
            if not isinstance(source_url, str):
                continue
            canonical = canonicalize_tourism_url(source_url)
            if canonical in seen:
                continue
            seen.add(canonical)
            candidates.append({
                "original_url": source_url,
                "canonical_url": canonical,
                "primary_category": "attraction_detail",
                "external_source_id": reference.get("source_attraction_id") or extract_external_source_id(canonical),
                "visible_link_text_original": reference.get("link_text_original"),
                "visible_link_text_normalized": reference.get("link_text_normalized"),
                "authorization_status": "approved_for_pilot",
                "human_review_status": "pending_review",
                "approval_basis": "researcher-confirmed approval for currently discovered official listing detail pages",
                "scope_limitation": "This manifest includes only detail URLs extracted from captured listing pages; it is not a website-completeness claim."
            })
    return {"stage": "10.1.3E_gate_5b_1", "status": "review_only_detail_batch_manifest",
            "source": str(extraction_path), "candidate_count": len(candidates),
            "proposed_follow_up_candidates": candidates}


def write_detail_batches(*, manifest: dict, reports_dir: Path, batch_size: int = 3) -> list[Path]:
    if batch_size < 1 or batch_size > 3:
        raise ValueError("Gate 5B first-pilot batch size must be between one and three")
    reports_dir.mkdir(parents=True, exist_ok=True)
    candidates = manifest["proposed_follow_up_candidates"]
    paths: list[Path] = []
    for index in range(0, len(candidates), batch_size):
        batch = candidates[index:index + batch_size]
        plan = {
            "approval_reference": None,
            "researcher_execution_approved_at": None,
            "emergency_stop": False,
            "approved_urls": [{"canonical_url": item["canonical_url"], "authorization_status": "approved_for_pilot",
                               "researcher_review_status": "pending_review", "approval_reference": None} for item in batch]
        }
        path = reports_dir / f"stage_10_1_3e_gate5b1_detail_batch_{len(paths) + 1:02d}.json"
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        paths.append(path)
    return paths
