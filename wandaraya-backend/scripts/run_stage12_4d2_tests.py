#!/usr/bin/env python3
"""Behavioral and persisted-data tests for Stage 12.4D.2."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from collections import Counter
from sqlalchemy import create_engine, text

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/"data"/"reports"
EVAL=ROOT/"data"/"evaluation"
POLICY="12.4d2_v1.2"
engine=create_engine(os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya"),future=True)

def load_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def read_csv(name):
    with (EVAL/name).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def count(sql,params=None):
    with engine.connect() as c:return c.execute(text(sql),params or {}).scalar_one()
def require(value,message="assertion failed"):
    if not value: raise AssertionError(message)

manifest=load_json(EVAL/"stage12_4d2_dataset_manifest.json")
checksums=load_json(EVAL/"stage12_4d2_dataset_checksums.json")
recon=load_json(REPORTS/"stage12_4d2_evidence_reconciliation.json")
sampling=load_json(EVAL/"stage12_4d2_review_sampling_manifest.json")
cohort_a=read_csv("stage12_4d2_cohort_a_high_evidence.csv")
cohort_b=read_csv("stage12_4d2_cohort_b_inferred.csv")
cohort_c=read_csv("stage12_4d2_cohort_c_provisional.csv")
monthly=read_csv("stage12_4d2_monthly_evaluation_dataset.csv")
mapping_review=read_csv("stage12_4d2_mapping_review_blind.csv")
season_review=read_csv("stage12_4d2_seasonality_review_blind.csv")

def t01(): require(count("SELECT version_num FROM alembic_version") in {"e12f3a4b5c6d","f23a4b5c6d7e","g34b5c6d7e8f"})
def t02(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings")==10127)
def t03(): require(count("SELECT count(*) FROM climate_daily_observations")==165828)
def t04(): require(count("SELECT count(*) FROM climate_district_monthly_aggregates")==4800 and count("SELECT count(*) FROM climate_district_monthly_climatology")==300)
def t05(): require(recon["contradictory_metric_instances"]>0)
def t06(): require(recon["mandatory_discrepancy_conclusion"]["result_b"].startswith("Found in narrative"))
def t07(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings WHERE evidence_tier IS NULL OR evidence_policy_version IS NULL")==0)
def t08(): require(count("SELECT count(*) FROM climate_mapping_evidence_audit WHERE policy_version=:p",{"p":POLICY})==10127)
def t09(): require(count("SELECT count(*) FROM climate_mapping_evidence_audit WHERE original_mapping_status='PROVISIONAL' AND policy_version=:p",{"p":POLICY})==4728)
def t10(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings WHERE evidence_tier='C' AND is_eligible_for_offline_evaluation")==0)
def t11(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings WHERE mapping_validation_status='UNSUPPORTED' AND is_eligible_for_offline_evaluation")==0)
def t12(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings WHERE independent_review_status<>'NOT_REVIEWED'")==0)
def t13(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings WHERE evaluation_eligibility_status IS NULL")==0)
def t14(): require(all(r["evidence_tier"]=="A" and r["evaluation_eligibility"]=="ELIGIBLE_HIGH_EVIDENCE" for r in cohort_a))
def t15(): require(all(r["evaluation_eligibility"]=="ELIGIBLE_INFERRED" for r in cohort_b))
def t16(): require(all(r["evaluation_eligibility"] not in ("ELIGIBLE_HIGH_EVIDENCE","ELIGIBLE_INFERRED") for r in cohort_c))
def t17():
    sets=[{(r['attraction_id'],r['activity_type_id']) for r in x} for x in (cohort_a,cohort_b,cohort_c)]
    require(not (sets[0]&sets[1] or sets[0]&sets[2] or sets[1]&sets[2]))
def t18(): require(len(cohort_a)+len(cohort_b)+len(cohort_c)==10127)
def t19(): require(len({(r['attraction_id'],r['activity_id'],r['calendar_month']) for r in monthly})==len(monthly))
def t20(): require(all(1<=int(r["calendar_month"])<=12 for r in monthly))
def t21(): require(all(0<=float(r["climate_favorability_score"])<=1 for r in monthly))
def t22(): require(set(Counter((r['attraction_id'],r['activity_id']) for r in monthly).values())=={12})
def t23(): require(count("SELECT count(*) FROM climate_attraction_activity_seasonality s JOIN climate_attraction_activity_mappings m ON m.attraction_id=s.attraction_id AND m.activity_type_id=s.activity_type_id WHERE m.is_eligible_for_offline_evaluation AND NOT s.is_active")==0)
def t24(): require(all(r["source_dataset_id"] and r["historical_reference_period"] for r in monthly))
def t25(): require(all(r["geographic_source_type"] in ("ATTRACTION_COORDINATE_REANALYSIS","DISTRICT_REPRESENTATIVE_PROXY") for r in monthly))
def t26(): require(all(r["safety_abstention_status"] in ("ABSTAIN","NO_RECORDED_ABSTENTION") for r in monthly))
def t27(): require(all(not r["decision"] and not r["reviewer_id"] for r in mapping_review+season_review))
def t28():
    ids=[r["review_item_id"] for r in mapping_review]
    require(ids==sorted(ids,key=lambda x:int(x.split('-')[1])) and len(ids)==len(set(ids)))
def t29(): require(len(sampling["activity_coverage"])==16)
def t30():
    b=load_json(EVAL/"stage12_4d2_baseline_configuration_manifest.json")
    require(set(b["baselines"])==set("ABCDE") and b["weights_modified"] is False)
def t31(): require(manifest["dataset_version"]=="stage12_4d2_eval_v1" and manifest["immutable"] is True)
def t32():
    for name,digest in checksums["files"].items(): require(hashlib.sha256((EVAL/name).read_bytes()).hexdigest()==digest,name)
def t33(): require(checksums["deterministic_double_export_verified"] is True)
def t34(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings WHERE evidence_policy_version=:p",{"p":POLICY})==10127)
def t35():
    with engine.connect() as c:
        tx=c.begin(); old=c.execute(text("SELECT evidence_tier FROM climate_attraction_activity_mappings WHERE id=1")).scalar_one(); c.execute(text("UPDATE climate_attraction_activity_mappings SET evidence_tier='D' WHERE id=1")); tx.rollback()
    require(count("SELECT evidence_tier FROM climate_attraction_activity_mappings WHERE id=1")==old)
def t36(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings m LEFT JOIN attractions a ON a.id=m.attraction_id LEFT JOIN climate_activity_types t ON t.id=m.activity_type_id WHERE a.id IS NULL OR t.id IS NULL")==0)
def t37():
    source=(ROOT/"scripts"/"run_stage12_4d2_evaluation_readiness.py").read_text(encoding="utf-8").lower()
    require("qdrant_client" not in source and "http://qdrant" not in source and "6333" not in source)
def t38(): require("ranking_weight" not in (ROOT/"scripts"/"run_stage12_4d2_evaluation_readiness.py").read_text(encoding="utf-8").lower())
def t39(): require("weather_readings" not in (ROOT/"scripts"/"run_stage12_4d2_evaluation_readiness.py").read_text(encoding="utf-8").lower())
def t40(): require(count("SELECT count(*) FROM climate_seasonality_quality_audit")==1187)
def t41(): require(count("SELECT count(*) FROM climate_attraction_activity_seasonality")==121524)
def t42(): require(count("SELECT count(*) FROM climate_attraction_activity_mappings WHERE mapping_validation_status='PROVISIONAL'")==4686)
def t43(): require(count("SELECT count(*) FROM climate_mapping_evidence_audit WHERE provisional_audit_class='PROVISIONAL_CONTRADICTORY' AND policy_version=:p",{"p":POLICY})==42)
def t44(): require(len(monthly)==len(cohort_a+cohort_b)*12)
def t45(): require(all(r["evaluation_cohort"] in ("A","B") for r in monthly))
def t46(): require(all("climate_favorability" not in k and "score" not in k for k in mapping_review[0].keys()))
def t47(): require(all("score" not in k and "class" not in k and "rank" not in k for k in season_review[0].keys()))
def t48(): require(manifest["git_commit_hash"] and len(manifest["git_commit_hash"])==40)
def t49(): require(manifest["alembic_revision"]=="e12f3a4b5c6d")
def t50():
    protocol=(ROOT/"docs"/"research"/"STAGE_12_4E_EVALUATION_PROTOCOL.md").read_text(encoding="utf-8")
    require("Prepared, Not Executed" in protocol and "until genuine independent labels exist" in protocol)

TESTS=[(f"test_{i:02d}",globals()[f"t{i:02d}"]) for i in range(1,51)]
results=[]
for name,fn in TESTS:
    try: fn(); results.append({"name":name,"status":"PASS"}); print(f"PASS {name}")
    except Exception as exc: results.append({"name":name,"status":"FAIL","error":str(exc)}); print(f"FAIL {name}: {exc}")
passed=sum(r["status"]=="PASS" for r in results)
report={"status":"ALL_TESTS_PASSED" if passed==len(TESTS) else "TESTS_FAILED","stage":"12.4D.2","total_tests":len(TESTS),"passed":passed,"failed":len(TESTS)-passed,"results":results}
(REPORTS/"stage12_4d2_tests.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps({k:report[k] for k in ("status","total_tests","passed","failed")},indent=2))
sys.exit(0 if passed==len(TESTS) else 1)
