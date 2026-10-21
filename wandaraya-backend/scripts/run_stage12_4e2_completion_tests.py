#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,json,os,sys
from collections import Counter,defaultdict
from pathlib import Path
import psycopg
ROOT=Path(__file__).resolve().parents[1];R=ROOT/"data"/"reports";O=ROOT/"data"/"evaluation"/"stage12_4e2"
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def db(sql,args=()):
 with psycopg.connect(dsn()) as c:
  with c.cursor() as q:q.execute(sql,args);return q.fetchone()[0]
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def rows(p):
 with Path(p).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def req(v,msg="assertion failed"):
 if not v:raise AssertionError(msg)
gt=rows(O/"stage12_4e2_ground_truth_v1.csv");manifest=load(O/"stage12_4e2_ground_truth_manifest.json");agreement=load(R/"stage12_4e2_reviewer_agreement.json");ranking=load(R/"stage12_4e2_ranking_evaluation.json");baseline=load(R/"stage12_4e2_baseline_comparison.json");ablation=load(R/"stage12_4e2_ablation_evaluation.json");cluster=load(R/"stage12_4e2_cluster_statistics.json");summary=load(R/"stage12_4e2_final_summary.json")
tests=[]
def t(name,fn):tests.append((name,fn))
t("migration_head",lambda:req(db("SELECT version_num FROM alembic_version")=="h45c6d7e8f9a"))
t("two_reviewers",lambda:req(db("SELECT count(DISTINCT reviewer_id) FROM climate_reviewer_label_submissions WHERE dataset_version='stage12_4e2_review_v1'")==2))
t("genuine_labels_1650",lambda:req(db("SELECT count(*) FROM climate_reviewer_label_submissions WHERE dataset_version='stage12_4e2_review_v1'")==1650))
t("assignments_1650",lambda:req(db("SELECT count(*) FROM climate_review_assignments WHERE review_dataset_version='stage12_4e2_review_v1'")==1650))
t("all_finalized",lambda:req(db("SELECT count(*) FROM climate_review_assignments WHERE review_dataset_version='stage12_4e2_review_v1' AND status<>'FINALIZED'")==0))
t("no_duplicate_submissions",lambda:req(db("SELECT count(*) FROM (SELECT task_type,review_item_id,reviewer_id,count(*) FROM climate_reviewer_label_submissions WHERE dataset_version='stage12_4e2_review_v1' GROUP BY 1,2,3 HAVING count(*)>1)x")==0))
t("mapping_adjudications",lambda:req(db("SELECT count(*) FROM climate_adjudicated_labels WHERE dataset_version='stage12_4e2_review_v1' AND task_type='mapping'")==22))
t("seasonality_adjudications",lambda:req(db("SELECT count(*) FROM climate_adjudicated_labels WHERE dataset_version='stage12_4e2_review_v1' AND task_type='seasonality'")==113))
t("adjudication_evidence",lambda:req(db("SELECT count(*) FROM climate_adjudicated_labels WHERE dataset_version='stage12_4e2_review_v1' AND evidence_json::jsonb='{}'::jsonb")==0))
t("mapping_overlap",lambda:req(agreement["tasks"]["mapping"]["overlap"]==105));t("seasonality_overlap",lambda:req(agreement["tasks"]["seasonality"]["overlap"]==720))
t("mapping_disagreements",lambda:req(agreement["tasks"]["mapping"]["disagreements"]==22));t("seasonality_disagreements",lambda:req(agreement["tasks"]["seasonality"]["disagreements"]==113))
t("mapping_kappa_range",lambda:req(-1<=agreement["tasks"]["mapping"]["cohens_kappa"]["kappa"]<=1));t("seasonality_kappa_range",lambda:req(-1<=agreement["tasks"]["seasonality"]["cohens_kappa"]["kappa"]<=1))
t("weighted_kappa_range",lambda:req(-1<=agreement["tasks"]["seasonality"]["weighted_cohens_kappa_ordinal"]["kappa"]<=1))
t("gt_version",lambda:req(manifest["dataset_version"]=="stage12_4e2_ground_truth_v1"));t("gt_720",lambda:req(len(gt)==720));t("gt_60_queries",lambda:req(len({r["evaluation_query_id"] for r in gt})==60))
t("gt_12_each",lambda:req(all(v==12 for v in Counter(r["evaluation_query_id"] for r in gt).values())));t("gt_unresolved_zero",lambda:req(manifest["unresolved_disagreements"]==0))
t("gt_insufficient_96",lambda:req(manifest["insufficient_evidence_records"]==96));t("gt_rankable_52",lambda:req(manifest["fully_rankable_queries"]==52))
t("insufficient_not_zero",lambda:req(all(r["relevance_grade"]=="" for r in gt if r["label_completeness_status"]=="INSUFFICIENT_EVIDENCE")))
t("grade_range",lambda:req(all(r["relevance_grade"]=="" or 0<=int(float(r["relevance_grade"]))<=4 for r in gt)))
t("gt_checksum",lambda:req(hashlib.sha256((O/"stage12_4e2_ground_truth_v1.csv").read_bytes()).hexdigest()==manifest["csv_sha256"]))
t("gt_db_verified",lambda:req(db("SELECT status FROM climate_ground_truth_dataset_versions WHERE dataset_version='stage12_4e2_ground_truth_v1'")=="VERIFIED"))
t("ranking_computed",lambda:req(ranking["status"]=="COMPUTED"));t("ranking_52",lambda:req(ranking["fully_rankable_queries"]==52))
for metric in ("ndcg@3","ndcg@5","ndcg@12","spearman","kendall_tau_b","top3_overlap"):
 t("metric_"+metric,lambda metric=metric:req(ranking["metrics"]["activity_aware"][metric]["valid_queries"]==52))
t("primary_baseline",lambda:req(baseline["primary_comparison"]=="activity_aware_vs_district_multivariable"));t("baseline_n52",lambda:req(baseline["comparisons"]["district_multivariable"]["paired"]["n"]==52))
t("cluster_iterations",lambda:req(cluster["iterations"]==10000));t("cluster_small_warning",lambda:req("Small cluster counts" in cluster["limitation"]))
t("ablations_computed",lambda:req(ablation["status"]=="COMPUTED"));t("wind_not_invented",lambda:req(ablation["wind_ablation"]=="UNAVAILABLE_NO_NONZERO_WIND_WEIGHT"))
t("run_completed",lambda:req(db("SELECT status FROM climate_evaluation_runs WHERE run_version='stage12_4e2_run_v1'")=="HUMAN_EVALUATION_COMPLETED_VERIFIED"))
t("experiments_completed",lambda:req(db("SELECT count(*) FROM climate_evaluation_experiment_results e JOIN climate_evaluation_runs r ON r.id=e.run_id WHERE r.run_version='stage12_4e2_run_v1' AND e.status='COMPLETED'")==6))
t("raw_climate_preserved",lambda:req(db("SELECT count(*) FROM climate_daily_observations")==165828));t("predictions_preserved",lambda:req(db("SELECT count(*) FROM climate_evaluation_predictions")==606528));t("seasonality_preserved",lambda:req(db("SELECT count(*) FROM climate_attraction_activity_seasonality")==121524))
t("final_status",lambda:req(summary["status"]=="HUMAN_EVALUATION_COMPLETED_VERIFIED"));t("no_fabrication_claim",lambda:req("NO_FABRICATED_LABELS" in summary["integrity"]))
result=[]
for name,fn in tests:
 try:fn();result.append({"name":name,"status":"PASS"})
 except Exception as e:result.append({"name":name,"status":"FAIL","error":str(e)})
passed=sum(x["status"]=="PASS" for x in result);report={"status":"ALL_TESTS_PASSED" if passed==len(tests) else "TESTS_FAILED","total_tests":len(tests),"passed":passed,"failed":len(tests)-passed,"results":result}
(R/"stage12_4e2_completion_tests.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
if report["failed"]==0:
 final=load(R/"stage12_4e2_final_summary.json");final["completion_tests"]={k:report[k] for k in ("status","total_tests","passed","failed")};(R/"stage12_4e2_final_summary.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps({k:report[k] for k in ("status","total_tests","passed","failed")},indent=2));sys.exit(0 if report["failed"]==0 else 1)
