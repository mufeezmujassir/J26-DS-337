"""Create a verified Gate 5D checkpoint and bounded resumable batch plan."""
from __future__ import annotations
import argparse,json,subprocess,sys
from datetime import UTC, datetime
from pathlib import Path
from app.time_context.governance.google_places_orchestrator import checkpoint,discover_live_manifests,write_checkpoint

def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--queue",default="data/reports/stage_10_1_3e_gate5c_all_batches_v2_gate5c_v2_google_places_enrichment_queue.json");p.add_argument("--reports-dir",default="data/reports");p.add_argument("--checkpoint",default="data/reports/stage_10_1_3e_gate5d_checkpoint.json");p.add_argument("--batch-size",type=int,default=5);p.add_argument("--max-batches",type=int,default=1);p.add_argument("--manifests",nargs="*");p.add_argument("--batch-id-prefix");p.add_argument("--request-interval-seconds",type=float,default=1);p.add_argument("--max-retries",type=int,default=1);p.add_argument("--live",action="store_true");p.add_argument("--execute",action="store_true");p.add_argument("--confirm-execute",action="store_true")
 a=p.parse_args()
 if any((a.live,a.execute,a.confirm_execute)) and not all((a.live,a.execute,a.confirm_execute)):
  raise PermissionError("live orchestration requires --live --execute --confirm-execute")
 paths=[Path(x) for x in a.manifests] if a.manifests else discover_live_manifests(Path(a.reports_dir))
 value=checkpoint(queue_path=Path(a.queue),manifest_paths=paths,batch_size=a.batch_size);value["max_batches_per_invocation"]=a.max_batches;value["next_batches"]=value["planned_batches"][:a.max_batches];write_checkpoint(value,Path(a.checkpoint))
 if a.live:
  if value["retriable_records"]: raise RuntimeError("retriable API failures require review before live resume")
  prefix=a.batch_id_prefix or f"orchestrated_live_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
  for index in range(min(a.max_batches,len(value["planned_batches"]))):
   command=[sys.executable,"-m","scripts.run_srilanka_tourism_google_places_gate5d","--queue",a.queue,"--reports-dir",a.reports_dir,"--batch-id",f"{prefix}_{index+1:02d}","--max-records",str(a.batch_size),"--resume-manifest",a.checkpoint,"--request-interval-seconds",str(a.request_interval_seconds),"--max-retries",str(a.max_retries),"--include-details","--live","--execute","--confirm-execute"]
   subprocess.run(command,check=True)
   value=checkpoint(queue_path=Path(a.queue),manifest_paths=discover_live_manifests(Path(a.reports_dir)),batch_size=a.batch_size);value["max_batches_per_invocation"]=a.max_batches;value["next_batches"]=value["planned_batches"][:a.max_batches];write_checkpoint(value,Path(a.checkpoint))
 print(json.dumps({"mode":"live" if a.live else "dry_run","network_requests":0 if not a.live else "reported_by_child_batches","checkpoint":a.checkpoint,"progress":value["progress"],"next_batches":value["next_batches"],"postgresql_writes":False,"qdrant_writes":False},indent=2))
if __name__=="__main__":main()
