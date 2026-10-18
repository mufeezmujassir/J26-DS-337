"""Gate 5E.2B.1: deterministic, read-only human identity evidence package."""
from __future__ import annotations
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path
from app.time_context.governance.tourism_sync_approval import digest
def confidence(item):
 c=(item.get('candidates') or [{}])[0]; reasons=item.get('review_reasons') or []
 if item.get('classification') in {'related_locality_not_attraction','ambiguous_multiple_candidates'} or c.get('location_conflict'): return 'CONFLICTING_EVIDENCE'
 if item.get('proposed_action')=='LINK_SOURCE_REFERENCE_CANDIDATE': return 'STRONG_EVIDENCE'
 if item.get('proposed_action')=='INSERT_NEW_CANDIDATE' and c.get('score',0)>=.75:return 'MODERATE_EVIDENCE'
 return 'WEAK_EVIDENCE'
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',default='data/reports/stage_10_1_3e_gate5e1_all_completed_v1_consolidated_attraction_manifest.json');p.add_argument('--coverage',default='data/reports/stage_10_1_3e_gate5e1_all_completed_v1_coverage_summary.json');p.add_argument('--reports-dir',default='data/reports');p.add_argument('--batch-id',default='all_completed_v1');a=p.parse_args();plan=json.loads(Path(a.manifest).read_text())['records'];cov=json.loads(Path(a.coverage).read_text());
 if len(plan)!=82 or len({x['external_source_id'] for x in plan})!=82:raise ValueError('all 82 unique records are required')
 clusters=defaultdict(list)
 for x in plan:
  for c in x.get('candidates',[]):
   if c.get('google_place_id'):clusters[c['google_place_id']].append(x['external_source_id'])
 cases=[]
 for x in plan:
  c=(x.get('candidates') or [{}])[0]; dupe=[k for k,v in clusters.items() if x['external_source_id'] in v and len(v)>1]; level=confidence(x);missing=[k for k in ('official_name','official_source_url','google_place_id') if not x.get(k)]
  cases.append({'external_source_id':x['external_source_id'],'official_name':x.get('official_name'),'official_source_url':x.get('official_source_url'),'google_candidate_name':c.get('display_name'),'google_place_id':x.get('google_place_id'),'existing_kb_candidates':c.get('existing_kb_matches',[]),'classification':x.get('classification'),'proposed_action':x.get('proposed_action'),'confidence':level,'duplicate_cluster_ids':dupe,'identity_conflicts':x.get('review_reasons',[]),'missing_information':missing,'recommended_next_review_action':'VERIFY_AND_DECIDE','action_payload_sha256':digest(x),'checkpoint_sha256':cov['checkpoint_sha256'],'decision':'DEFER'})
 groups={'insertion_review_cases':[x for x in cases if x['proposed_action']=='INSERT_NEW_CANDIDATE'],'source_link_review_cases':[x for x in cases if x['proposed_action']=='LINK_SOURCE_REFERENCE_CANDIDATE'],'identity_conflict_cases':[x for x in cases if x['proposed_action']=='MANUAL_REVIEW_REQUIRED'],'duplicate_cluster_cases':[{'google_place_id':k,'source_ids':v,'recommendation':'Review whether records represent one physical attraction; do not merge automatically.'} for k,v in clusters.items() if len(v)>1]}
 out=Path(a.reports_dir);out.mkdir(parents=True,exist_ok=True); paths={}
 payloads={'identity_evidence_manifest':{'records':cases},**groups,'review_priority_queue':{'records':sorted(cases,key=lambda x:({'CONFLICTING_EVIDENCE':0,'WEAK_EVIDENCE':1,'MODERATE_EVIDENCE':2,'STRONG_EVIDENCE':3}[x['confidence']],x['external_source_id']))},'reviewer_decision_template':{'checkpoint_sha256':cov['checkpoint_sha256'],'decisions':[{'source_attraction_id':x['external_source_id'],'proposed_action':x['proposed_action'],'google_place_id':x['google_place_id'],'action_payload_sha256':x['action_payload_sha256'],'reviewer_identity':None,'decision':'DEFER','review_notes':None,'review_timestamp':None} for x in cases]},'approval_readiness_summary':{'total_records':len(cases),'confidence_counts':dict(Counter(x['confidence'] for x in cases)),'postgresql_writes':False,'qdrant_writes':False,'network_requests':0}}
 for k,v in payloads.items():
  path=out/f'stage_10_1_3e_gate5e2b1_{a.batch_id}_{k}.json';path.write_text(json.dumps(v,indent=2,sort_keys=True,default=str));paths[k]=str(path)
 csvpath=out/f'stage_10_1_3e_gate5e2b1_{a.batch_id}_reviewer_decision_workbook.csv'
 with csvpath.open('w',newline='',encoding='utf-8') as f:
  fields=['external_source_id','official_name','official_source_url','google_candidate_name','google_place_id','proposed_action','confidence','duplicate_cluster_ids','identity_conflicts','action_payload_sha256','checkpoint_sha256','decision','reviewer_identity','review_notes','review_timestamp'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();[w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in x.items() if k in fields}) for x in cases]
 paths['reviewer_decision_workbook']=str(csvpath);print(json.dumps({'mode':'read_only_evidence_review','records':len(cases),'reports':paths,'postgresql_writes':False,'qdrant_writes':False,'network_requests':0},indent=2))
if __name__=='__main__':main()
