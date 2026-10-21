#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,json,os,subprocess,sys
from collections import Counter,defaultdict
from pathlib import Path
import psycopg
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation.label_validation import validate_label,validate_independence
from app.climate.evaluation.reviewer_agreement import cohens_kappa,krippendorff_alpha
from app.climate.evaluation.review_workflow import assign_items,completion_status,finalize_assignment
from app.climate.evaluation.ranking_metrics import ndcg,spearman,kendall,top_k_overlap
from app.climate.evaluation.statistical_analysis import cluster_bootstrap
O=ROOT/"data"/"evaluation"/"stage12_4e2";R=ROOT/"data"/"reports"
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def rows(p):
 with Path(p).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def db(sql,args=()):
 with psycopg.connect(dsn()) as c:
  with c.cursor() as q:q.execute(sql,args);return q.fetchone()[0]
def req(x,msg="assertion failed"):
 if not x:raise AssertionError(msg)
m=rows(O/"reviewer_mapping_package.csv");s=rows(O/"reviewer_seasonality_package.csv");manifest=load(O/"review_sampling_manifest.json");checks=load(O/"review_package_checksums.json")["files"]
tests=[]
def test(name,fn):tests.append((name,fn))
test("migration_head",lambda:req(db("SELECT version_num FROM alembic_version")=="g34b5c6d7e8f"))
for table in ("climate_review_assignments","climate_reviewer_submission_corrections","climate_ground_truth_dataset_versions","climate_evaluation_artifact_references"):
 test("table_"+table,lambda table=table:req(db("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",(table,))==1))
test("mapping_105",lambda:req(len(m)==105));test("seasonality_720",lambda:req(len(s)==720))
test("mapping_unique",lambda:req(len({x['review_item_id'] for x in m})==105));test("seasonality_unique",lambda:req(len({x['review_item_id'] for x in s})==720))
test("pairs_60",lambda:req(len({(x['attraction_id'],x['activity_type_id']) for x in s})==60))
test("twelve_months",lambda:req(all(set(v)=={str(i) for i in range(1,13)} for v in defaultdict(list,{k:[x['calendar_month'] for x in s if (x['attraction_id'],x['activity_type_id'])==k] for k in {(x['attraction_id'],x['activity_type_id']) for x in s}}).values())))
test("manifest_version",lambda:req(manifest["review_dataset_version"]=="stage12_4e2_review_v1"));test("source_version",lambda:req(manifest["source_dataset_version"]=="stage12_4d2_eval_v1"))
test("planned_two_reviewers",lambda:req(manifest["planned_reviewers"]==2));test("planned_judgments",lambda:req(manifest["planned_judgments"]==1650))
test("all_activities",lambda:req(len({x['activity_type_id'] for x in s})==16));test("cohort_a_primary",lambda:req(Counter((x['attraction_id'],x['activity_type_id'],x['evaluation_cohort']) for x in s)))
for field in ("reviewer_id","reviewer_expertise","review_timestamp","evidence_reviewed","decision","confidence","notes"):
 test("mapping_blank_"+field,lambda field=field:req(all(not x[field] for x in m)));test("seasonality_blank_"+field,lambda field=field:req(all(not x[field] for x in s)))
for token in ("score","rank","class","evidence_tier","ablation","model"):
 test("mapping_blind_"+token,lambda token=token:req(not any(token in x.lower() for x in m[0])));test("seasonality_blind_"+token,lambda token=token:req(not any(token in x.lower() for x in s[0])))
for field in ("rainfall_mean_mm","rainfall_cv","temperature_mean_c","relative_humidity_mean_pct","solar_radiation_mean_mj","historical_reference_period","source_name","product_version"):
 test("evidence_"+field,lambda field=field:req(all(x[field] for x in s)))
for name,digest in checks.items():test("checksum_"+name,lambda name=name,digest=digest:req(hashlib.sha256((O/name).read_bytes()).hexdigest()==digest))
test("package_audit",lambda:req(load(R/"stage12_4e2_review_package_audit.json")["status"]=="PASS"))
test("labels_zero",lambda:req(db("SELECT count(*) FROM climate_reviewer_label_submissions WHERE dataset_version='stage12_4e2_review_v1'")==0))
test("persisted_assignment_integrity",lambda:req(db("SELECT count(*)-count(DISTINCT (task_type,review_item_id,reviewer_id)) FROM climate_review_assignments WHERE review_dataset_version='stage12_4e2_review_v1'")==0))
test("ground_truth_zero",lambda:req(db("SELECT count(*) FROM climate_ground_truth_dataset_versions WHERE review_sampling_version='stage12_4e2_review_v1'")==0))
test("run_ready",lambda:req(db("SELECT status FROM climate_evaluation_runs WHERE run_version='stage12_4e2_run_v1'")=="READY_AWAITING_REVIEWERS"))
test("experiments_pending",lambda:req(db("SELECT count(*) FROM climate_evaluation_experiment_results e JOIN climate_evaluation_runs r ON r.id=e.run_id WHERE r.run_version='stage12_4e2_run_v1' AND e.status='PENDING_HUMAN_REVIEW'")==6))
test("artifacts_six",lambda:req(db("SELECT count(*) FROM climate_evaluation_artifact_references a JOIN climate_evaluation_runs r ON r.id=a.run_id WHERE r.run_version='stage12_4e2_run_v1'")==5))
test("final_status",lambda:req(load(R/"stage12_4e2_final_summary.json")["status"]=="HUMAN_EVALUATION_READY_AWAITING_REVIEWERS"))
test("no_fabrication",lambda:req(load(R/"stage12_4e2_final_summary.json")["fabricated_labels"]==0))
test("agreement_pending",lambda:req(load(R/"stage12_4e2_reviewer_agreement.json")["status"]=="PENDING_HUMAN_REVIEW"))
test("stats_pending",lambda:req(load(R/"stage12_4e2_statistical_analysis.json")["status"]=="PENDING_HUMAN_REVIEW"))
test("kappa_perfect",lambda:req(cohens_kappa(["A","B"],["A","B"])["kappa"]==1))
test("kappa_insufficient",lambda:req(cohens_kappa([],[])["status"]=="INSUFFICIENT_OVERLAP"))
test("alpha_perfect",lambda:req(krippendorff_alpha([{"review_item_id":"1","decision":"A"},{"review_item_id":"1","decision":"A"},{"review_item_id":"2","decision":"B"},{"review_item_id":"2","decision":"B"}])["alpha"]==1))
test("alpha_insufficient",lambda:req(krippendorff_alpha([])["status"]=="INSUFFICIENT_OVERLAP"))
test("valid_mapping_label",lambda:req(validate_label({"review_item_id":"x","reviewer_id":"r","review_timestamp":"2026-01-01T00:00:00Z","decision":"SUPPORTED","evidence_reviewed":"e","confidence":"HIGH"},"mapping",{"x"},"v")["confidence"]=="HIGH"))
def invalid_confidence():
 try:validate_label({"review_item_id":"x","reviewer_id":"r","review_timestamp":"2026-01-01T00:00:00Z","decision":"SUPPORTED","evidence_reviewed":"e","confidence":"CERTAIN"},"mapping",{"x"},"v");req(False)
 except ValueError:pass
test("invalid_confidence",invalid_confidence)
def duplicate_rejected():
 try:validate_independence([{"review_item_id":"x","reviewer_id":"r"},{"review_item_id":"x","reviewer_id":"r"}]);req(False)
 except ValueError:pass
test("duplicate_rejected",duplicate_rejected)
test("cli_help",lambda:req(subprocess.run([sys.executable,str(ROOT/"scripts"/"manage_stage12_4e2_reviews.py"),"--help"],capture_output=True).returncode==0))
test("instructions_exist",lambda:req((O/"reviewer_instructions.md").stat().st_size>500))
test("correction_documented",lambda:req("correction" in (O/"reviewer_instructions.md").read_text(encoding="utf-8").lower()))
test("cluster_limit_documented",lambda:req("22 source identities" in (ROOT/"docs"/"research"/"STAGE_12_4E2_HUMAN_EVALUATION_REPORT.md").read_text(encoding="utf-8")))
def assignment_fixture(mode):
 item=m[0]["review_item_id"]
 with psycopg.connect(dsn()) as c:
  assign_items(c,"__isolated_test_reviewer__","mapping",[item])
  if mode=="integrity":req(completion_status(c,"__isolated_test_reviewer__","mapping")["assigned"]==1)
  elif mode=="idempotent":
   assign_items(c,"__isolated_test_reviewer__","mapping",[item]);req(completion_status(c,"__isolated_test_reviewer__","mapping")["assigned"]==1)
  elif mode=="incomplete":
   try:finalize_assignment(c,"__isolated_test_reviewer__","mapping");req(False)
   except ValueError:pass
  elif mode=="complete":
   with c.cursor() as q:q.execute("INSERT INTO climate_reviewer_label_submissions(dataset_version,task_type,review_item_id,reviewer_id,label,reviewed_at,evidence_json) VALUES('stage12_4e2_review_v1','mapping',%s,'__isolated_test_reviewer__','SUPPORTED',now(),%s)",(item,json.dumps({"fixture":True})))
   req(completion_status(c,"__isolated_test_reviewer__","mapping")["complete"]);finalize_assignment(c,"__isolated_test_reviewer__","mapping");req(completion_status(c,"__isolated_test_reviewer__","mapping")["assignment_statuses"]=={"FINALIZED":1})
  c.rollback()
test("assignment_integrity",lambda:assignment_fixture("integrity"));test("assignment_idempotency",lambda:assignment_fixture("idempotent"));test("partial_finalize_rejected",lambda:assignment_fixture("incomplete"));test("complete_finalize",lambda:assignment_fixture("complete"))
test("fixture_rollback",lambda:req(db("SELECT count(*) FROM climate_review_assignments WHERE reviewer_id='__isolated_test_reviewer__'")==0))
test("ndcg_correct",lambda:req(ndcg([1,2,3],{1:3,2:2,3:1},3)==1));test("spearman_correct",lambda:req(spearman([1,2,3],[1,2,3])==1));test("kendall_correct",lambda:req(kendall([1,2,3],[1,2,3])==1));test("top3_correct",lambda:req(top_k_overlap([1,2,3],[2,3,4],3)==2/3))
test("missing_judgment",lambda:req(ndcg([1,2,3],{1:3},3) is None));test("cluster_bootstrap_query_clusters",lambda:req(cluster_bootstrap({"c1":[1,2],"c2":[3,4]},iterations=50)["clusters"]==2))
test("activity_subgroups_present",lambda:req(all(v>=1 for v in Counter((x['activity_type_id'],x['attraction_id']) for x in s).values())));test("geographic_subgroups_present",lambda:req(set(x['climate_source_type'] for x in s)<= {"DISTRICT_REPRESENTATIVE_PROXY","ATTRACTION_COORDINATE_REANALYSIS"}))
results=[]
for name,fn in tests:
 try:fn();results.append({"name":name,"status":"PASS"})
 except Exception as e:results.append({"name":name,"status":"FAIL","error":str(e)})
passed=sum(x["status"]=="PASS" for x in results);report={"status":"ALL_TESTS_PASSED" if passed==len(tests) else "TESTS_FAILED","total_tests":len(tests),"passed":passed,"failed":len(tests)-passed,"pytest_limitation":"pytest is not installed in the Docker image; no pytest suite is claimed as passed.","results":results}
(R/"stage12_4e2_tests.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8");print(json.dumps({k:report[k] for k in ("status","total_tests","passed","failed","pytest_limitation")},indent=2));sys.exit(0 if report["failed"]==0 else 1)
