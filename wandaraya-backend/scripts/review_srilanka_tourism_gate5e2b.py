"""Create Gate 5E.2B review reports and a default-DEFER decision template."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from app.time_context.governance.tourism_sync_approval import digest,validate_approval_file
def main():
 p=argparse.ArgumentParser();p.add_argument('--prefix',default='data/reports/stage_10_1_3e_gate5e1_all_completed_v1');p.add_argument('--reports-dir',default='data/reports');p.add_argument('--batch-id',default='all_completed_v1');p.add_argument('--decisions');a=p.parse_args();prefix=Path(a.prefix)
 manifest=json.loads(Path(str(prefix)+'_consolidated_attraction_manifest.json').read_text()); coverage=json.loads(Path(str(prefix)+'_coverage_summary.json').read_text()); plan=manifest['records']
 if len(plan)!=coverage['expected_source_records'] or len({x['external_source_id'] for x in plan})!=len(plan):raise ValueError('incomplete or duplicate Gate 5E.1 input')
 inserts=[x for x in plan if x['proposed_action']=='INSERT_NEW_CANDIDATE'];links=[x for x in plan if x['proposed_action']=='LINK_SOURCE_REFERENCE_CANDIDATE'];conflicts=[x for x in plan if x['proposed_action']=='MANUAL_REVIEW_REQUIRED']
 insertion=[{**x,'readiness':'INSERT_READY_FOR_REVIEW' if x.get('google_place_id') else 'INSUFFICIENT_EVIDENCE'} for x in inserts]; linking=[{**x,'readiness':'LINK_READY_FOR_REVIEW'} for x in links]
 template={'checkpoint_sha256':coverage['checkpoint_sha256'],'decisions':[{'source_attraction_id':x['external_source_id'],'proposed_action':x['proposed_action'],'target_attraction_id':None,'google_place_id':x.get('google_place_id'),'action_payload_sha256':digest(x),'reviewer_identity':None,'decision':'DEFER','review_notes':None,'review_timestamp':None} for x in plan]}
 approval={'approved_actions':[],'blocked_actions':[],'writes':False,'qdrant_writes':False,'network_requests':0} if not a.decisions else validate_approval_file(plan=plan,approval=json.loads(Path(a.decisions).read_text()),checkpoint_sha256=coverage['checkpoint_sha256'])
 payloads={'insertion_readiness':{'records':insertion},'source_link_readiness':{'records':linking},'identity_conflicts':{'records':conflicts},'duplicate_review':json.loads(Path(str(prefix)+'_duplicate_cluster_report.json').read_text()),'reviewer_decision_template':template,'approval_validation':approval,'approved_action_manifest':{'records':approval['approved_actions'],'writes':False},'deferred_rejected_actions':{'records':template['decisions'] if not a.decisions else approval['blocked_actions']},'summary':{'total_reviewed_records':len(plan),'ready_for_review_insertions':len(insertion),'ready_for_review_links':len(linking),'manual_review_blockers':len(conflicts),'approved_actions':len(approval['approved_actions']),'deferred_actions':len(template['decisions']) if not a.decisions else 0,'rejected_actions':0,'duplicate_conflicts':len(json.loads(Path(str(prefix)+'_duplicate_cluster_report.json').read_text()).get('records',[])),'postgresql_attraction_writes':False,'qdrant_writes':False,'external_api_requests':0}}
 out=Path(a.reports_dir);out.mkdir(parents=True,exist_ok=True);paths={}
 for k,v in payloads.items():
  path=out/f'stage_10_1_3e_gate5e2b_{a.batch_id}_{k}.json';path.write_text(json.dumps(v,indent=2,sort_keys=True,default=str));paths[k]=str(path)
 print(json.dumps({'mode':'read_only_review','records':len(plan),'postgresql_writes':False,'qdrant_writes':False,'network_requests':0,'reports':paths},indent=2))
if __name__=='__main__':main()
