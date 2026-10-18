"""Gate 5E.2B.4 targeted verification; offline default, live requires explicit flags."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from app.time_context.governance.tourism_sync_approval import digest
def main():
 p=argparse.ArgumentParser();p.add_argument('--proposals',default='data/reports/stage_10_1_3e_gate5e2b3_all_completed_v1_corrected_proposals_v3.json');p.add_argument('--evidence',default='data/reports/stage_10_1_3e_gate5e2b1_all_completed_v1_identity_evidence_manifest.json');p.add_argument('--reports-dir',default='data/reports');p.add_argument('--batch-id',default='all_completed_v1');p.add_argument('--max-requests',type=int,default=60);p.add_argument('--live',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--confirm-execute',action='store_true');a=p.parse_args()
 if any((a.live,a.execute,a.confirm_execute)): raise PermissionError('live verification is intentionally not enabled by this offline review runner; use the existing bounded Gate 5D runner after explicit authorization')
 records=json.loads(Path(a.proposals).read_text())['records']; names={x['external_source_id']:x.get('official_name') for x in json.loads(Path(a.evidence).read_text())['records']};blocked=[x for x in records if x['v3_resolution']=='REMAIN_UNRESOLVED'];
 if len(records)!=82 or len(blocked)!=30:raise ValueError('expected 82 records and 30 unresolved cases')
 queue=[]
 for x in blocked:
  source=x['source_attraction_id'];name=names.get(source);queue.append({'source_attraction_id':source,'official_name':name,'previous_google_place_id':x.get('corrected_google_place_id'),'queries':[name] if name else [],'priority':'high','max_api_requests':2,'missing_evidence':['independent candidate search','shortlisted place details'],'status':'pending'})
 budget={'mode':'offline','unresolved_records':30,'per_record_max_requests':2,'maximum_request_budget':min(a.max_requests,60),'estimated_requests':min(60,a.max_requests),'network_requests':0}
 v4=[]
 for x in records:
  y={**x,'proposal_version':'v4','new_evidence_collected':False,'candidate_verification_result':'NO_VALID_GOOGLE_CANDIDATE' if x in blocked else 'PRESERVED_PRIOR_EVIDENCE','reviewer_status':'DEFER'};y['v4_proposal_sha256']=digest(y);v4.append(y)
 out=Path(a.reports_dir);out.mkdir(parents=True,exist_ok=True);template={'decisions':[{'source_attraction_id':x['source_attraction_id'],'v4_proposal_sha256':x['v4_proposal_sha256'],'decision':'DEFER','reviewer_identity':None,'review_timestamp':None,'review_notes':None} for x in v4]};payloads={'targeted_live_verification_queue':{'records':queue},'api_request_budget':budget,'live_verification_checkpoint':{'completed_source_ids':[],'pending_source_ids':[x['source_attraction_id'] for x in queue],'network_requests':0},'google_places_candidate_results':{'records':[]},'identity_verification_results':{'records':[]},'duplicate_cluster_verification':{'records':[],'status':'requires_human_review'},'corrected_proposals_v4':{'records':v4},'reviewer_decision_template':template,'approval_validation':{'approved_actions':[]},'approved_action_manifest':{'records':[],'integrity':'valid_empty_manifest'},'gate5e2c_preflight':{'status':'NOT_READY_FOR_SYNC','reasons':['no live verification evidence','no explicit approvals','30 unresolved records']},'summary':{'total_records':82,'unresolved_queued':30,'planned_api_request_budget':budget['estimated_requests'],'approved_actions':0,'postgresql_writes':False,'qdrant_writes':False,'network_requests':0}}
 paths={}
 for k,v in payloads.items():path=out/f'stage_10_1_3e_gate5e2b4_{a.batch_id}_{k}.json';path.write_text(json.dumps(v,indent=2,sort_keys=True));paths[k]=str(path)
 import csv
 csvpath=out/f'stage_10_1_3e_gate5e2b4_{a.batch_id}_reviewer_decision_workbook.csv'
 with csvpath.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(template['decisions'][0]));w.writeheader();w.writerows(template['decisions'])
 paths['reviewer_decision_workbook']=str(csvpath);print(json.dumps({'mode':'offline','records':82,'unresolved_queued':30,'reports':paths,'postgresql_writes':False,'qdrant_writes':False,'network_requests':0},indent=2))
if __name__=='__main__':main()
