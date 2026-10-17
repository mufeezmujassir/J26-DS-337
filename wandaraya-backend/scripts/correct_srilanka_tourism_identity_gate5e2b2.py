"""Offline Gate 5E.2B.2 correction proposals from immutable cached evidence."""
from __future__ import annotations
import argparse,csv,json,re
from collections import Counter,defaultdict
from pathlib import Path
from app.time_context.governance.tourism_sync_approval import digest
SUSPICIOUS={'105','107','111','114','124','128','135','142','148','149','211','51','6'}
def kind(name):
 n=(name or '').lower()
 if re.search(r'\s(&|/|and)\s',n):return 'COMPOUND_ATTRACTION'
 if any(x in n for x in ('watching','craft village')):return 'TOURISM_ACTIVITY'
 if any(x in n for x in ('unawatuna','meemure','kataragama','kosgoda')):return 'DESTINATION_OR_LOCALITY'
 return 'SINGLE_PHYSICAL_ATTRACTION'
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',default='data/reports/stage_10_1_3e_gate5e1_all_completed_v1_consolidated_attraction_manifest.json');p.add_argument('--evidence',default='data/reports/stage_10_1_3e_gate5e2b1_all_completed_v1_identity_evidence_manifest.json');p.add_argument('--reports-dir',default='data/reports');p.add_argument('--batch-id',default='all_completed_v1');a=p.parse_args(); plan={x['external_source_id']:x for x in json.loads(Path(a.manifest).read_text())['records']};ev=json.loads(Path(a.evidence).read_text())['records']
 if len(plan)!=82 or len(ev)!=82 or set(plan)!={x['external_source_id'] for x in ev}:raise ValueError('incomplete or inconsistent immutable inputs')
 corrected=[]; reassessment=[]; clusters=defaultdict(list)
 for e in ev:
  source=e['external_source_id']; sid=source.rsplit(':',1)[-1]; original=plan[source]; outcome='KEEP_CURRENT_GOOGLE_CANDIDATE'; action=original['proposed_action']; reason='cached evidence has no stronger replacement candidate'
  if sid in SUSPICIOUS or e['classification']=='related_locality_not_attraction': outcome='REMOVE_UNRELIABLE_GOOGLE_CANDIDATE';action='MANUAL_REVIEW_REQUIRED';reason='cached result is suspicious, locality/service-like, or source identity is not established'
  elif kind(e['official_name'])!='SINGLE_PHYSICAL_ATTRACTION': outcome='MULTIPLE_PLAUSIBLE_CANDIDATES';action='MANUAL_REVIEW_REQUIRED';reason='official source describes a compound, activity, or destination rather than one POI'
  cp={'source_attraction_id':source,'original_proposed_action':original['proposed_action'],'corrected_proposed_action':action,'original_google_place_id':original.get('google_place_id'),'corrected_google_place_id':None if outcome=='REMOVE_UNRELIABLE_GOOGLE_CANDIDATE' else original.get('google_place_id'),'existing_kb_target_attraction_id':None,'candidate_reassessment':outcome,'attraction_kind':kind(e['official_name']),'correction_reason':reason,'original_proposal_sha256':digest(original),'checkpoint_sha256':e['checkpoint_sha256'],'human_review_status':'DEFER'};cp['corrected_proposal_sha256']=digest(cp);corrected.append(cp);reassessment.append({'source_attraction_id':source,'outcome':outcome,'original_candidate':e.get('google_place_id'),'all_cached_candidates':e.get('existing_kb_candidates',[]),'reason':reason})
  if e.get('google_place_id'):clusters[e['google_place_id']].append(source)
 dup=[{'google_place_id':k,'source_ids':v,'proposed_resolution':'INSUFFICIENT_EVIDENCE' if set(x.rsplit(':',1)[-1] for x in v)=={'107','124'} else 'SAME_PHYSICAL_ATTRACTION','requires_explicit_reviewer_decision':True} for k,v in clusters.items() if len(v)>1]
 out=Path(a.reports_dir);out.mkdir(parents=True,exist_ok=True);template={'decisions':[{'source_attraction_id':x['source_attraction_id'],'corrected_proposal_hash':x['corrected_proposal_sha256'],'checkpoint_sha256':x['checkpoint_sha256'],'decision':'DEFER','reviewer_identity':None,'review_timestamp':None,'review_notes':None} for x in corrected]};payloads={'identity_correction_manifest':{'records':corrected},'google_candidate_reassessment':{'records':reassessment},'existing_kb_duplicate_assessment':{'records':[],'note':'No new database queries were made; existing cached evidence only.'},'duplicate_cluster_resolution_cases':{'records':dup},'locality_and_compound_attraction_cases':{'records':[x for x in corrected if x['attraction_kind']!='SINGLE_PHYSICAL_ATTRACTION']},'corrected_sync_proposals':{'records':corrected},'corrected_reviewer_decision_template':template,'approval_validation':{'approved_actions':[],'writes':False},'approved_action_manifest':{'records':[],'writes':False},'unresolved_identity_blockers':{'records':[x for x in corrected if x['corrected_proposed_action']=='MANUAL_REVIEW_REQUIRED']},'summary':{'total_records':82,'unchanged_candidates':sum(x['candidate_reassessment']=='KEEP_CURRENT_GOOGLE_CANDIDATE' for x in corrected),'corrected_google_candidates':0,'removed_unreliable_candidates':sum(x['candidate_reassessment']=='REMOVE_UNRELIABLE_GOOGLE_CANDIDATE' for x in corrected),'reclassified_proposed_actions':sum(x['original_proposed_action']!=x['corrected_proposed_action'] for x in corrected),'duplicate_clusters':len(dup),'unresolved_identity_conflicts':sum(x['corrected_proposed_action']=='MANUAL_REVIEW_REQUIRED' for x in corrected),'approved_actions':0,'deferred_actions':82,'rejected_actions':0,'postgresql_attraction_writes':False,'qdrant_writes':False,'external_api_requests':0}}
 paths={}
 for k,v in payloads.items():path=out/f'stage_10_1_3e_gate5e2b2_{a.batch_id}_{k}.json';path.write_text(json.dumps(v,indent=2,sort_keys=True));paths[k]=str(path)
 csvpath=out/f'stage_10_1_3e_gate5e2b2_{a.batch_id}_corrected_reviewer_workbook.csv'
 with csvpath.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(template['decisions'][0]));w.writeheader();w.writerows(template['decisions'])
 paths['corrected_reviewer_workbook']=str(csvpath);print(json.dumps({'mode':'offline_identity_correction','records':82,'reports':paths,'postgresql_writes':False,'qdrant_writes':False,'network_requests':0},indent=2))
if __name__=='__main__':main()
