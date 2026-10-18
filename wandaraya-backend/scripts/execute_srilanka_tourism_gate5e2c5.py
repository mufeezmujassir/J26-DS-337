"""Gate 5E.2C.5 controlled executor; dry-run by default."""
from __future__ import annotations
import argparse, asyncio, json
from pathlib import Path
from typing import Any
from sqlalchemy import select, text
from scripts.sync_srilanka_tourism_gate5e2c3 import digest, file_digest, write_json
from app.database import AsyncSessionLocal
from app.models.attraction import Attraction
from app.models.attraction_categories import AttractionCategory
from app.models.tourism_sync import AttractionSourceReference, AttractionFieldProvenance, TourismImportBatch, TourismSyncReview

BASE="data/reports/stage_10_1_3e_gate5e2c4_all_completed_v1_"
ORIGINAL="data/reports/stage_10_1_3e_gate5e2c2_all_completed_v1_reapproved_action_manifest.json"

def load(path: str) -> dict[str, Any]: return json.loads(Path(path).read_text(encoding="utf-8"))

def canonical_scope(scope: dict[str, Any]) -> dict[str, Any]:
    return {k:v for k,v in scope.items() if k != "write_scope_sha256"}

def canonical_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {k:v for k,v in plan.items() if k != "execution_plan_sha256"}

def validate(scope: dict[str, Any], plan: dict[str, Any], integrity: dict[str, Any], original_path: str) -> list[str]:
    reasons=[]; records=scope.get("records",[]); ids=[r.get("source_attraction_id") for r in records]
    if digest(canonical_scope(scope)) != scope.get("write_scope_sha256"): reasons.append("write_scope_hash_mismatch")
    if digest(canonical_plan(plan)) != plan.get("execution_plan_sha256"): reasons.append("execution_plan_hash_mismatch")
    if file_digest(Path(original_path)) != integrity.get("source_manifest_sha256"): reasons.append("original_approval_manifest_hash_mismatch")
    if len(records)!=24: reasons.append("write_scope_count_must_be_24")
    if len(ids)!=len(set(ids)) or "srilanka_tourism_attraction:89" in ids: reasons.append("invalid_or_excluded_source_in_scope")
    for row in records:
        if not all(row.get(key) is not None for key in ("name","google_place_id","district_id","category_id","latitude","longitude","official_source_url")): reasons.append(f"incomplete_payload:{row.get('source_attraction_id')}")
    return sorted(set(reasons))

async def collisions(records: list[dict[str, Any]]) -> tuple[int,list[dict[str,Any]]]:
    ids={r["source_attraction_id"] for r in records}; places={r["google_place_id"] for r in records}
    async with AsyncSessionLocal() as s:
        count=len((await s.execute(select(Attraction.id).where(Attraction.is_active.is_(True)))).scalars().all())
        existing=(await s.execute(select(Attraction.id,Attraction.name,Attraction.google_place_id).where(Attraction.google_place_id.in_(places)))).all()
        refs=(await s.execute(select(AttractionSourceReference.external_source_id,AttractionSourceReference.attraction_id).where(AttractionSourceReference.source_provider=="srilanka_tourism",AttractionSourceReference.external_source_id.in_(ids)))).all()
    audit=[]
    for attraction_id,name,place in existing: audit.append({"type":"existing_google_place_id","google_place_id":place,"attraction_id":attraction_id,"name":name})
    for source_id,attraction_id in refs: audit.append({"type":"existing_source_reference","source_attraction_id":source_id,"attraction_id":attraction_id})
    return count,audit

async def commit_scope(*, records:list[dict[str,Any]], batch_id:str, manifest_hash:str) -> list[int]:
    """Future-only atomic writer. Caller must complete all C.5 authorizations."""
    async with AsyncSessionLocal() as s:
        async with s.begin():
            await s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),{"key":"srilanka-tourism-gate5e2c5"})
            existing=(await s.execute(select(AttractionSourceReference.external_source_id).where(AttractionSourceReference.source_provider=="srilanka_tourism",AttractionSourceReference.external_source_id.in_([r["source_attraction_id"] for r in records])))).scalars().all()
            if existing: raise RuntimeError("idempotency_or_concurrent_source_reference_conflict")
            s.add(TourismImportBatch(batch_id=batch_id,source_provider="srilanka_tourism",input_manifest_sha256=manifest_hash,input_checkpoint_sha256="verified_c4_scope",queue_sha256=digest(records),status="running",approved_action_count=len(records),proposed_insert_count=len(records)))
            inserted=[]
            for row in records:
                a=Attraction(name=row["name"],slug=row["slug"],google_place_id=row["google_place_id"],district_id=row["district_id"],latitude=row["latitude"],longitude=row["longitude"],location=row["location"],is_active=True)
                s.add(a); await s.flush(); inserted.append(a.id)
                s.add(AttractionCategory(attraction_id=a.id,category_id=row["category_id"],is_primary=True,confidence_score=1.0))
                ref=AttractionSourceReference(attraction_id=a.id,source_provider="srilanka_tourism",external_source_id=row["source_attraction_id"],canonical_source_url=row["official_source_url"],source_title=row["name"],identity_status="reviewed_verified",import_batch_id=batch_id)
                s.add(ref); await s.flush()
                for field in row["field_provenance"]: s.add(AttractionFieldProvenance(attraction_id=a.id,source_reference_id=ref.id,field_name=field,source_provider="srilanka_tourism",source_record_id=row["source_attraction_id"],value_fingerprint=digest(row.get(field)),import_batch_id=batch_id,approval_reference="gate5e2c5"))
                s.add(TourismSyncReview(import_batch_id=batch_id,source_attraction_id=row["source_attraction_id"],proposed_action="INSERT_NEW_CANDIDATE",source_manifest_sha256=manifest_hash,action_payload_sha256=digest(row),approval_status="committed",reviewer_identity="approved_c4_scope"))
            return inserted

def main():
 p=argparse.ArgumentParser(); p.add_argument("--batch-id",default="all_completed_v1");p.add_argument("--dry-run",action="store_true");p.add_argument("--execute",action="store_true");p.add_argument("--confirm-execute",action="store_true");p.add_argument("--manifest-sha256");p.add_argument("--write-scope-sha256");p.add_argument("--plan-sha256");p.add_argument("--approved-count",type=int);p.add_argument("--reports-dir",default="data/reports");a=p.parse_args()
 scope=load(BASE+"final_write_scope_manifest.json"); plan=load(BASE+"final_execution_plan.json"); integrity=load(BASE+"write_scope_integrity.json"); reasons=validate(scope,plan,integrity,ORIGINAL)
 if a.execute:
  expected=[("--manifest-sha256",a.manifest_sha256,integrity["source_manifest_sha256"]),("--write-scope-sha256",a.write_scope_sha256,scope["write_scope_sha256"]),("--plan-sha256",a.plan_sha256,plan["execution_plan_sha256"])]
  if not a.confirm_execute or a.approved_count!=24 or any(got!=want for _,got,want in expected) or reasons: p.error("execution authorization validation failed")
  p.error("live transaction is implemented but deliberately disabled for this task; obtain separate authorization and enable it in the next execution stage")
 count,audit=asyncio.run(collisions(scope["records"])); ready=not reasons and not audit
 out={"authorization_validation":{"valid":not reasons,"reasons":reasons},"pretransaction_collision_audit":{"records":audit,"collision_free":not audit},"transaction_plan":{"planned_records":len(scope["records"]),"atomic":True,"rollback_on_error":True,"writes_executed":False},"dry_run_summary":{"ready":ready,"existing_attraction_count":count,"expected_attraction_count":count+len(scope["records"]),"postgresql_writes_executed":False,"qdrant_writes_executed":False,"external_api_requests":0},"idempotency_validation":{"key":"srilanka_tourism + external_source_id","status":"not_previously_imported" if not audit else "requires_review"},"transaction_safety_tests":{"write_mode_not_invoked":True,"qdrant_writes":False},"reconciliation_plan":{"verify_records":len(scope["records"]),"excluded_source_id":"srilanka_tourism_attraction:89"},"execution_authorization_requirements":{"manifest_sha256":integrity["source_manifest_sha256"],"write_scope_sha256":scope["write_scope_sha256"],"plan_sha256":plan["execution_plan_sha256"],"approved_count":24},"summary":{"ready_insertions":len(scope["records"]),"collision_free":not audit,"postgresql_writes_executed":False,"qdrant_writes_executed":False,"external_api_requests":0}}
 prefix=Path(a.reports_dir)/f"stage_10_1_3e_gate5e2c5_{a.batch_id}_"; paths={}
 for key,val in out.items(): path=prefix.with_name(prefix.name+key+".json");write_json(path,val);paths[key]=str(path)
 print(json.dumps({"mode":"dry_run","summary":out["summary"],"reports":paths},indent=2))
if __name__=="__main__":main()
