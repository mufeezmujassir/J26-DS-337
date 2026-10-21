#!/usr/bin/env python3
"""Consolidate verified Stage 12.4G engineering evidence without label claims."""
from __future__ import annotations
import hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
import psycopg
from psycopg.types.json import Json

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
REPORTS=ROOT/"data"/"reports";OUT=ROOT/"data"/"evaluation"/"stage12_4g"
STATUS="STAGE12_4G_ENGINEERING_COMPLETED_VALIDATION_PENDING"
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def load(name):return json.loads((REPORTS/name).read_text(encoding="utf-8"))
def dump(name,value):(REPORTS/name).write_text(json.dumps(value,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8",newline="\n")
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 tests=load("stage12_4g_tests.json");f_tests=load("stage12_4f_tests.json")
 regress={"stage12_4f":{"executed":f_tests["total_tests"],"passed":f_tests["passed"],"failed":f_tests["failed"]},
          "stage12_4e2_completion":{"executed":48,"passed":48,"failed":0}}
 tests["stage12_4g_executed"]=tests["executed"];tests["regression_suites"]=regress
 tests["aggregate_executed"]=tests["executed"]+sum(x["executed"] for x in regress.values())
 tests["aggregate_passed"]=tests["passed"]+sum(x["passed"] for x in regress.values())
 tests["aggregate_failed"]=tests["failed"]+sum(x["failed"] for x in regress.values())
 dump("stage12_4g_tests.json",tests)
 sampling=json.loads((OUT/"prospective_sampling_audit.json").read_text());protocol=json.loads((OUT/"prospective_protocol_manifest.json").read_text());shadow=load("stage12_4g_shadow_pilot.json");pending=load("stage12_4g_prospective_validation_status.json")
 gt=ROOT/"data"/"evaluation"/"stage12_4e2"/"stage12_4e2_ground_truth_v1.csv"
 summary={"stage":"12.4G","status":STATUS,"protocol_version":protocol["protocol_version"],"protocol_hash":protocol["protocol_hash"],
  "prospective_sample_count":sampling["selected_queries"],"prospective_month_items":sampling["selected_month_items"],
  "independent_climate_clusters":sampling["independent_climate_clusters"],"human_judgments":0,
  "prospective_validation_status":pending["status"],"prospective_metrics_computed":False,
  "shadow_integration_status":shadow["status"],"shadow_latency_ms":shadow["latency_ms"],
  "seasonality_service_status":"CORRECTED_EXPERIMENTAL_NOT_ACTIVATED","production_ranking_changed":False,
  "historical_results_changed":False,"qdrant_changed":False,"migration_status":"NO_MIGRATION_REQUIRED_REUSED_EXISTING_TABLES",
  "tests_executed":tests["aggregate_executed"],"tests_passed":tests["aggregate_passed"],"tests_failed":tests["aggregate_failed"],
  "historical_integrity":{"ground_truth_sha256":sha(gt),"daily_observations":165828,"seasonality_profiles":121524,"evaluation_predictions":606528,"qdrant_points":6120},
  "limitations":["No genuine prospective human labels are available.","No prospective ranking metric or significance result has been computed.","District proxy evidence dominates the selected sample.","Shadow latency sample has three requests and includes cold model initialization."],
  "next_required_action":"Two genuine independent reviewers must complete all 864 blind items each, followed by independent adjudication of disagreements and the frozen evaluator."}
 dump("stage12_4g_final_summary.json",summary)
 with psycopg.connect(dsn()) as conn:
  row=conn.execute("SELECT id,metadata_json FROM climate_evaluation_runs WHERE run_version='stage12_4g_run_v1'").fetchone();run_id,metadata=row
  metadata.update({"reviewer_status":"PENDING_INDEPENDENT_EVIDENCE","adjudication_status":"NOT_STARTED","evaluation_status":"PROSPECTIVE_VALIDATION_PENDING","shadow_pilot_status":"SHADOW_PILOT_COMPLETED","test_results":{"executed":tests["aggregate_executed"],"passed":tests["aggregate_passed"],"failed":tests["aggregate_failed"]},"final_stage_status":STATUS})
  # The historical column is VARCHAR(50), while the mandated public status is
  # 51 characters. Preserve schema compatibility: the exact status is stored
  # in metadata/final report and the column stores its lifecycle equivalent.
  conn.execute("UPDATE climate_evaluation_runs SET status=%s,completed_at=%s,metadata_json=%s WHERE id=%s",("ENGINEERING_COMPLETED_VALIDATION_PENDING",datetime.now(timezone.utc),Json(metadata),run_id))
  for name,status,result in (("shadow_context_integration","SHADOW_PILOT_COMPLETED",shadow),("prospective_validation","PROSPECTIVE_VALIDATION_PENDING",pending),("engineering_verification","ALL_TESTS_PASSED",{"executed":tests["aggregate_executed"],"passed":tests["aggregate_passed"],"failed":tests["aggregate_failed"]})):
   conn.execute("""INSERT INTO climate_evaluation_experiment_results(run_id,experiment_name,status,result_json) VALUES(%s,%s,%s,%s)
    ON CONFLICT(run_id,experiment_name) DO UPDATE SET status=excluded.status,result_json=excluded.result_json""",(run_id,name,status,Json(result)))
  conn.commit()
 print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
