from __future__ import annotations
import argparse,json
from pathlib import Path
from app.time_context.governance.gate5e_sync_planning import consolidate_checkpoint,write_reports
def main():
 p=argparse.ArgumentParser();p.add_argument('--checkpoint',default='data/reports/stage_10_1_3e_gate5d_checkpoint.json');p.add_argument('--queue',default='data/reports/stage_10_1_3e_gate5c_all_batches_v2_gate5c_v2_google_places_enrichment_queue.json');p.add_argument('--reports-dir',default='data/reports');p.add_argument('--batch-id',default='all_completed_v1');a=p.parse_args()
 cp,q=Path(a.checkpoint),Path(a.queue);plan=consolidate_checkpoint(json.loads(cp.read_text()),json.loads(q.read_text()));paths=write_reports(plan=plan,checkpoint_path=cp,queue_path=q,reports_dir=Path(a.reports_dir),batch_id=a.batch_id);print(json.dumps({'mode':'read_only_sync_plan','records':len(plan),'postgresql_writes':False,'qdrant_writes':False,'network_requests':0,'reports':{k:str(v) for k,v in paths.items()}},indent=2))
if __name__=='__main__':main()
