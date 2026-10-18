"""Read-only approval validation for Gate 5E.2A."""
import hashlib,json
from typing import Any
from app.time_context.governance.gate5e_sync_planning import REVIEW_ACTIONS
def digest(value:Any)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def validate_approval_file(*,plan:list[dict],approval:dict,checkpoint_sha256:str)->dict:
 by_id={x['external_source_id']:x for x in plan}; seen=set(); approved=[]; blocked=[]
 for decision in approval.get('decisions',[]):
  source=decision.get('source_attraction_id'); action=decision.get('decision')
  if source in seen: raise ValueError('duplicate approval for source attraction')
  seen.add(source); item=by_id.get(source)
  if not item or action not in REVIEW_ACTIONS or decision.get('checkpoint_sha256')!=checkpoint_sha256: raise ValueError('stale or invalid approval')
  if action.startswith('APPROVE') and not decision.get('reviewer_identity'): raise ValueError('reviewer identity is required for approval')
  if decision.get('action_payload_sha256')!=digest(item): raise ValueError('approval payload was modified')
  if item['proposed_action']=='MANUAL_REVIEW_REQUIRED' and action.startswith('APPROVE'): blocked.append({**decision,'reason':'unresolved_identity_conflict'});continue
  approved.append(decision)
 return {'approved_actions':approved,'blocked_actions':blocked,'writes':False,'qdrant_writes':False,'network_requests':0}
