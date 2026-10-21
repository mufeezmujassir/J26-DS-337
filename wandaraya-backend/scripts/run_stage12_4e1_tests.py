#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,json,os,sys,tempfile
from pathlib import Path
import psycopg
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));F=ROOT/"data"/"evaluation";O=F/"stage12_4e1";R=ROOT/"data"/"reports"
from app.climate.evaluation.ablations import build_ablation_configurations,weighted_score
from app.climate.evaluation.baselines import deterministic_ranks
from app.climate.evaluation.label_validation import validate_independence,validate_label
from app.climate.evaluation.reviewer_agreement import cohens_kappa
from app.climate.evaluation.ranking_metrics import kendall,ndcg,spearman,top_k_overlap
from app.climate.evaluation.statistical_analysis import cluster_bootstrap
from app.climate.evaluation.leakage_audit import blind_template_exposure,verify_checksums
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def db(sql,args=()):
 with psycopg.connect(dsn()) as c:
  with c.cursor() as q:q.execute(sql,args);return q.fetchone()[0]
def req(v,m="assertion failed"):
 if not v:raise AssertionError(m)
manifest=load(F/"stage12_4d2_dataset_manifest.json");checks=verify_checksums(F,F/"stage12_4d2_dataset_checksums.json");configs=load(O/"stage12_4e1_model_configurations.json");abl=load(O/"stage12_4e1_ablation_configurations.json")["configurations"]
def csv_count(p):
 with Path(p).open(encoding="utf-8",newline="") as f:return sum(1 for _ in f)-1
def t01():req(checks["all_match"])
def t02():req(manifest["dataset_version"]=="stage12_4d2_eval_v1")
def t03():req(manifest["counts"]["cohorts"]=={"A":1267,"B":2945,"C":5915})
def t04():req(csv_count(F/"stage12_4d2_monthly_evaluation_dataset.csv")==50544)
def t05():req(db("SELECT count(*) FROM (SELECT attraction_id,activity_type_id,model_configuration_id,count(DISTINCT month) n FROM climate_evaluation_predictions GROUP BY 1,2,3 HAVING count(DISTINCT month)<>12)x")==0)
def t06():req(db("SELECT count(*) FROM climate_activity_types")==16)
def t07():req(len({(c["model_identifier"],c.get("model_version") or c.get("version")) for c in configs})==len(configs))
def t08():req(deterministic_ranks([{"calendar_month":1,"x":.2},{"calendar_month":2,"x":.8}],"x")=={2:1,1:2})
def t09():req(next(c for c in configs if c["model_identifier"]=="district_multivariable")["version"]=="12.4c_v1")
def t10():req("rainfall mean + 0.5" in next(c for c in configs if c["model_identifier"]=="rainfall_risk_adjusted")["definition"])
def t11():req(db("SELECT count(*) FROM climate_evaluation_predictions p JOIN climate_evaluation_model_configurations c ON c.id=p.model_configuration_id WHERE c.model_identifier='activity_aware' AND (p.score<0 OR p.score>1)")==0)
def t12():req(db("SELECT count(*) FROM (SELECT model_configuration_id,attraction_id,activity_type_id,array_agg(rank ORDER BY rank) a FROM climate_evaluation_predictions GROUP BY 1,2,3 HAVING array_agg(rank ORDER BY rank)<>ARRAY[1,2,3,4,5,6,7,8,9,10,11,12])x")==0)
def t13():req(deterministic_ranks([{"calendar_month":2,"x":1},{"calendar_month":1,"x":1}],"x")=={1:1,2:2})
def t14():req(len(abl)==9 and sum(c["available"] for c in abl)==8)
def t15():req(weighted_score({"a":1,"b":0},{"a":.5,"b":.5},["a"])==0)
def t16():req(abs(weighted_score({"a":1,"b":0},{"a":.2,"b":.3},[])-.4)<1e-9)
def t17():req(db("SELECT count(*) FROM climate_evaluation_predictions")==606528)
def t18():req(db("SELECT count(*) FROM climate_evaluation_predictions WHERE score<0 OR score>1")==0)
def t19():req(db("SELECT count(*) FROM climate_evaluation_predictions WHERE score IS NULL")==0)
def t20():req(abs(ndcg([1,2,3],{1:3,2:2,3:1},3)-1)<1e-9)
def t21():req(spearman([1,2,3],[1,2,3])==1)
def t22():req(kendall([1,2,3],[1,2,3])==1)
def t23():req(top_k_overlap([1,2,3],[2,3,4],3)==2/3)
def t24():req(ndcg([1,2,3],{1:3},3) is None)
def t25():req(db("SELECT count(*) FROM climate_reviewer_label_submissions")==0)
def t26():req(validate_label({"review_item_id":"x","reviewer_id":"r","review_timestamp":"2026-01-01T00:00:00+00:00","decision":"SUPPORTED","evidence_reviewed":"source","confidence":"HIGH"},"mapping",{"x"},"v")["decision"]=="SUPPORTED")
def t27():
 try:validate_independence([{"review_item_id":"x","reviewer_id":"r"},{"review_item_id":"x","reviewer_id":"r"}]);req(False)
 except ValueError:pass
def t28():
 try:validate_label({"review_item_id":"x","reviewer_id":"r","review_timestamp":"2026-01-01T00:00:00+00:00","decision":"MADE_UP","evidence_reviewed":"s","confidence":"HIGH"},"mapping",{"x"},"v");req(False)
 except ValueError:pass
def t29():req(("x","r1")!=("x","r2"))
def t30():req(cohens_kappa(["A","B"],["A","B"])["kappa"]==1)
def t31():req(cluster_bootstrap({"d1":[1,2],"d2":[3,4]},iterations=50)["clusters"]==2)
def t32():req(load(R/"stage12_4e1_geographic_proxy_analysis.json")["distinct_districts"]==20)
def t33():req(load(R/"stage12_4e1_leakage_audit.json")["shared_district_proxy"]=="DETECTED_AND_GROUPING_REQUIRED")
def t34():req(load(R/"stage12_4e1_cohort_sensitivity.json")["A"]["pairs"]==1267 and load(R/"stage12_4e1_cohort_sensitivity.json")["B"]["pairs"]==2945)
def t35():req(load(R/"stage12_4e1_geographic_proxy_analysis.json")["monthly_rows"]["DISTRICT_REPRESENTATIVE_PROXY"]==50484)
def t36():req(db("SELECT count(*) FROM climate_evaluation_predictions WHERE geographic_source='' OR geographic_source IS NULL")==0)
def t37():req(load(R/"stage12_4e1_leakage_audit.json")["status"]=="NO_CRITICAL_LEAKAGE_DETECTED")
def t38():req(blind_template_exposure(F/"stage12_4d2_mapping_review_blind.csv")["safe"] and blind_template_exposure(F/"stage12_4d2_seasonality_review_blind.csv")["safe"])
def t39():req(len({c["configuration_hash"] for c in configs})==len(configs))
def t40():
 expected=load(O/"stage12_4e1_prediction_checksums.json")["files"]
 for name,digest in expected.items():req(hashlib.sha256((O/name).read_bytes()).hexdigest()==digest)
def t41():req(db("SELECT count(*)-count(DISTINCT (run_id,model_configuration_id,attraction_id,activity_type_id,month)) FROM climate_evaluation_predictions")==0)
def t42():
 with psycopg.connect(dsn()) as c:
  q=c.cursor();q.execute("BEGIN");old=db("SELECT status FROM climate_evaluation_runs WHERE run_version='stage12_4e1_run_v1'");q.execute("UPDATE climate_evaluation_runs SET status='MUTATED' WHERE run_version='stage12_4e1_run_v1'");q.execute("ROLLBACK")
 req(db("SELECT status FROM climate_evaluation_runs WHERE run_version='stage12_4e1_run_v1'")==old)
def t43():req(db("SELECT count(*) FROM climate_evaluation_predictions p LEFT JOIN attractions a ON a.id=p.attraction_id LEFT JOIN climate_activity_types t ON t.id=p.activity_type_id WHERE a.id IS NULL OR t.id IS NULL")==0)
def t44():req(db("SELECT count(*) FROM climate_daily_observations")==165828)
def t45():req(verify_checksums(F,F/"stage12_4d2_dataset_checksums.json")["all_match"])
def t46():req("qdrant_client" not in (ROOT/"scripts"/"run_stage12_4e1_offline_evaluation.py").read_text(encoding="utf-8").lower())
def t47():req("ranking_weight" not in (ROOT/"scripts"/"run_stage12_4e1_offline_evaluation.py").read_text(encoding="utf-8").lower())
def t48():req(load(R/"stage12_4e1_human_label_readiness.json")["label_dependent_experiments_status"]=="PENDING_INDEPENDENT_HUMAN_LABELS")
def t49():req(load(R/"stage12_4d_tests.json")["passed"]==30)
def t50():req(load(R/"stage12_4d1_tests.json")["passed"]==40)
def t51():req(csv_count(O/"baseline_predictions.csv")==202176)
def t52():req(csv_count(O/"ablation_predictions.csv")==404352)
TESTS=[(f"test_{i:02}",globals()[f"t{i:02}"]) for i in range(1,53)];results=[]
for n,fn in TESTS:
 try:fn();results.append({"name":n,"status":"PASS"})
 except Exception as e:results.append({"name":n,"status":"FAIL","error":str(e)})
passed=sum(x["status"]=="PASS" for x in results);report={"status":"ALL_TESTS_PASSED" if passed==len(TESTS) else "TESTS_FAILED","total_tests":len(TESTS),"passed":passed,"failed":len(TESTS)-passed,"pytest_limitation":"pytest is not installed in the Docker image; no pytest suite is claimed as passed.","results":results};(R/"stage12_4e1_tests.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8");print(json.dumps({k:report[k] for k in ("status","total_tests","passed","failed","pytest_limitation")},indent=2));sys.exit(0 if report["failed"]==0 else 1)
