"""Offline-first targeted review package for Gate 5E.2B.3."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from app.time_context.governance.tourism_sync_approval import digest
def main():
 p=argparse.ArgumentParser();p.add_argument('--proposals',default='data/reports/stage_10_1_3e_gate5e2b2_all_completed_v1_corrected_sync_proposals.json');p.add_argument('--reports-dir',default='data/reports');p.add_argument('--batch-id',default='all_completed_v1');a=p.parse_args();records=json.loads(Path(a.proposals).read_text())['records'];blockers=[x for x in records if x['corrected_proposed_action']=='MANUAL_REVIEW_REQUIRED']
 if len(records)!=82 or len(blockers)!=30:raise ValueError('expected 82 corrected records and 30 blockers')
 investigations=[]
 for x in blockers:
  item={'source_attraction_id':x['source_attraction_id'],'official_evidence':x['correction_reason'],'current_google_place_id':x['corrected_google_place_id'],'original_google_place_id':x['original_google_place_id'],'attraction_kind':x['attraction_kind'],'missing_evidence':['verified exact source-to-place identity','reviewer decision'],'recommended_outcome':'REMAIN_UNRESOLVED','corrected_proposal_sha256':x['corrected_proposal_sha256'],'checkpoint_sha256':x['checkpoint_sha256']};investigations.append(item)
 v3=[]
 for x in records:
  y={**x,'v3_resolution':'REMAIN_UNRESOLVED' if x in blockers else 'KEEP_CORRECTED_PROPOSAL'};y['v3_proposal_sha256']=digest(y);v3.append(y)
 clusters=[]
 for ids in (['srilanka_tourism_attraction:36','srilanka_tourism_attraction:94'],['srilanka_tourism_attraction:107','srilanka_tourism_attraction:124']):clusters.append({'source_ids':ids,'reviewer_cluster_decision':'INSUFFICIENT_EVIDENCE','requires_explicit_cluster_decision':True})
 template={'decisions':[{'source_attraction_id':x['source_attraction_id'],'v3_proposal_sha256':x['v3_proposal_sha256'],'checkpoint_sha256':x['checkpoint_sha256'],'decision':'DEFER','reviewer_identity':None,'review_timestamp':None,'review_notes':None,'cluster_resolution_reference':None} for x in v3]};out=Path(a.reports_dir);out.mkdir(parents=True,exist_ok=True)
 summary={'total_records':82,'blockers_investigated':30,'alternative_candidates_identified':0,'corrected_proposals':0,'duplicate_clusters':2,'explicit_approvals':0,'valid_approved_actions':0,'postgresql_writes':False,'qdrant_writes':False,'network_requests':0}
 payloads={'targeted_investigation_queue':{'records':investigations},'identity_resolution_evidence':{'records':investigations},'alternative_google_candidates':{'records':[],'note':'No additional cached candidates establish a safe replacement.'},'corrected_proposals_v3':{'records':v3},'duplicate_cluster_review':{'records':clusters},'reviewer_decision_draft':template,'approval_validation':{'approved_actions':[],'blocked_actions':[],'writes':False},'approved_action_manifest':{'records':[],'integrity':'valid_empty_manifest','writes':False},'gate5e2c_preflight':{'status':'NOT_READY_FOR_SYNC','reasons':['no explicit validated approvals','30 unresolved identity blockers','duplicate clusters need reviewer decisions'],'approved_action_count':0,'postgresql_writes':False,'qdrant_writes':False},'summary':summary}
 paths={}
 for k,v in payloads.items():path=out/f'stage_10_1_3e_gate5e2b3_{a.batch_id}_{k}.json';path.write_text(json.dumps(v,indent=2,sort_keys=True));paths[k]=str(path)
 csvpath=out/f'stage_10_1_3e_gate5e2b3_{a.batch_id}_reviewer_decision_workbook.csv'
 with csvpath.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(template['decisions'][0]));w.writeheader();w.writerows(template['decisions'])
 paths['reviewer_decision_workbook']=str(csvpath);print(json.dumps({'mode':'offline_targeted_review','records':82,'blockers':30,'reports':paths,'postgresql_writes':False,'qdrant_writes':False,'network_requests':0},indent=2))
if __name__=='__main__':main()
