"""Gate 5E.1 deterministic, read-only synchronization planning."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any

REVIEW_ACTIONS={"APPROVE_UPDATE","APPROVE_INSERT","APPROVE_LINK","REJECT","DEFER"}

def resolve_action(item: dict[str,Any])->tuple[str,list[str]]:
    classification=item.get("classification"); reasons=list(item.get("review_reasons") or [])
    candidates=item.get("candidates") or []; top=candidates[0] if candidates else {}
    if classification in {"related_locality_not_attraction","ambiguous_multiple_candidates","high_confidence_candidate_review"} or top.get("location_conflict"):
        return "MANUAL_REVIEW_REQUIRED", reasons or [classification]
    if item.get("google_candidate_kb_identity")=="verified_existing_kb_place" and item.get("official_source_candidate_identity")=="strong_candidate_identity_evidence":
        return "LINK_SOURCE_REFERENCE_CANDIDATE", ["Google Place equals existing KB identity; source link still needs approval"]
    if classification=="new_google_place_candidate": return "INSERT_NEW_CANDIDATE", ["Google candidate is unapproved; insertion requires review"]
    if classification=="no_google_place_match": return "NO_CHANGE", ["no Google candidate returned"]
    if classification=="api_error": return "REJECT_INVALID_MATCH", ["API error; no synchronization proposal"]
    return "MANUAL_REVIEW_REQUIRED", reasons or ["insufficient identity evidence"]

def consolidate_checkpoint(checkpoint:dict[str,Any], queue:dict[str,Any])->list[dict[str,Any]]:
    expected={str(r.get("external_source_id")):r for r in queue.get("records",[])}; seen={};
    for item in checkpoint.get("results",[]):
        source=str(item.get("external_source_id"));
        if source in seen: raise ValueError(f"duplicate checkpoint source id: {source}")
        if source not in expected: raise ValueError(f"checkpoint source id is absent from queue: {source}")
        action,reasons=resolve_action(item); source_record=expected[source]; top=(item.get("candidates") or [{}])[0]
        seen[source]={"external_source_id":source,"official_name":source_record.get("attraction_name"),"official_source_url":source_record.get("source_url"),"google_place_id":top.get("google_place_id"),"google_candidate_kb_identity":item.get("google_candidate_kb_identity"),"official_source_candidate_identity":item.get("official_source_candidate_identity"),"classification":item.get("classification"),"proposed_action":action,"review_reasons":reasons,"candidates":item.get("candidates",[]),"details":item.get("details"),"source_provenance":item.get("source_provenance"),"approval_status":"unapproved","field_provenance":{"official":source_record,"google":top}}
    missing=sorted(set(expected)-set(seen));
    if missing: raise ValueError(f"checkpoint incomplete; missing {len(missing)} source records")
    return [seen[key] for key in sorted(seen)]

def validate_decisions(decisions:dict[str,Any], plan:list[dict[str,Any]])->list[dict[str,Any]]:
    by_id={x["external_source_id"]:x for x in plan}; validated=[]
    for d in decisions.get("decisions",[]):
        source=str(d.get("external_source_id")); action=d.get("decision")
        if action not in REVIEW_ACTIONS or source not in by_id: raise ValueError("invalid review decision")
        if d.get("google_place_id") != by_id[source].get("google_place_id"): raise ValueError("review decision Google Place ID mismatch")
        validated.append({**d,"validated":True})
    return validated

def write_reports(*, plan:list[dict[str,Any]], checkpoint_path:Path, queue_path:Path, reports_dir:Path, batch_id:str)->dict[str,Path]:
    reports_dir.mkdir(parents=True,exist_ok=True); groups=defaultdict(list)
    for item in plan: groups[item["proposed_action"]].append(item)
    duplicates=defaultdict(list)
    for item in plan:
        if item.get("google_place_id"): duplicates[item["google_place_id"]].append(item["external_source_id"])
    duplicate_clusters=[{"google_place_id":k,"external_source_ids":v,"review_action":"manual_review"} for k,v in sorted(duplicates.items()) if len(v)>1]
    summary={"expected_source_records":len(plan),"consolidated_source_records":len(plan),"missing_source_records":[],"duplicate_source_ids":[],"action_counts":dict(Counter(x["proposed_action"] for x in plan)),"unresolved_identity_conflicts":sum(x["proposed_action"]=="MANUAL_REVIEW_REQUIRED" for x in plan),"review_required_records":sum(x["proposed_action"]=="MANUAL_REVIEW_REQUIRED" for x in plan),"proposed_updates":len(groups["UPDATE_EXISTING_CANDIDATE"]),"proposed_insertions":len(groups["INSERT_NEW_CANDIDATE"]),"proposed_source_links":len(groups["LINK_SOURCE_REFERENCE_CANDIDATE"]),"postgresql_writes":False,"qdrant_writes":False,"network_requests":0,"checkpoint_sha256":sha256(checkpoint_path.read_bytes()).hexdigest(),"queue_sha256":sha256(queue_path.read_bytes()).hexdigest()}
    payloads={"consolidated_attraction_manifest":{"records":plan},"identity_resolution_results":{"records":plan},"duplicate_cluster_report":{"records":duplicate_clusters},"proposed_existing_attraction_updates":{"records":groups["UPDATE_EXISTING_CANDIDATE"]},"proposed_new_attraction_insertions":{"records":groups["INSERT_NEW_CANDIDATE"]},"proposed_source_reference_links":{"records":groups["LINK_SOURCE_REFERENCE_CANDIDATE"]},"manual_review_queue":{"records":groups["MANUAL_REVIEW_REQUIRED"]},"field_provenance_and_conflicts":{"records":[{"external_source_id":x["external_source_id"],"field_provenance":x["field_provenance"],"conflicts":x["review_reasons"]} for x in plan]},"database_schema_readiness":{"ready":False,"missing_capabilities":["multiple source references","field-level provenance","import batch identity","approval and duplicate-review history"],"recommended_migration":"Propose a separate reviewed migration; do not apply in Gate 5E.1."},"postgresql_synchronization_dry_run_manifest":{"records":plan,"writes":False},"coverage_summary":summary}
    paths={}
    for n,p in payloads.items():
        path=reports_dir/f"stage_10_1_3e_gate5e1_{batch_id}_{n}.json";path.write_text(json.dumps(p,indent=2,sort_keys=True,default=str),encoding="utf-8");paths[n]=path
    return paths
