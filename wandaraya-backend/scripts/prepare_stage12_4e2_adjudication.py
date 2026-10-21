#!/usr/bin/env python3
"""Calculate genuine reviewer agreement and prepare disagreement-only adjudication files."""
from __future__ import annotations

import csv, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation.reviewer_agreement import cohens_kappa,krippendorff_alpha

VERSION="stage12_4e2_review_v1"
OUT=ROOT/"data"/"evaluation"/"stage12_4e2"
REPORT=ROOT/"data"/"reports"/"stage12_4e2_reviewer_agreement.json"
TEMPLATES={"mapping":OUT/"attraction_activity_review.csv","seasonality":OUT/"reviewer_seasonality_package.csv"}
ORDINAL={"VERY_UNFAVORABLE","UNFAVORABLE","NEUTRAL","FAVORABLE","VERY_FAVORABLE"}
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def template(task):
    with TEMPLATES[task].open(encoding="utf-8-sig",newline="") as f:return {r["review_item_id"]:r for r in csv.DictReader(f)}
def write_csv(path,rows,fields):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)
def main():
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT s.task_type,s.review_item_id,s.reviewer_id,s.label,s.reviewed_at,s.evidence_json
                FROM climate_reviewer_label_submissions s JOIN climate_review_assignments a
                  ON a.review_dataset_version=s.dataset_version AND a.task_type=s.task_type
                 AND a.review_item_id=s.review_item_id AND a.reviewer_id=s.reviewer_id
                WHERE s.dataset_version=%s AND a.status='FINALIZED' AND s.reviewer_id IN ('R001','R002')
                ORDER BY s.task_type,s.review_item_id,s.reviewer_id""",(VERSION,));raw=cur.fetchall()
    by_task={"mapping":{},"seasonality":{}}
    rows_for_alpha={"mapping":[],"seasonality":[]}
    for task,item,reviewer,label,reviewed_at,evidence in raw:
        by_task[task].setdefault(item,{})[reviewer]={"label":label,"reviewed_at":reviewed_at.isoformat(),"evidence":evidence}
        rows_for_alpha[task].append({"review_item_id":item,"reviewer_id":reviewer,"decision":label})
    report={"stage":"12.4E.2","review_dataset_version":VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),"status":"ADJUDICATION_REQUIRED","tasks":{}}
    for task in ("mapping","seasonality"):
        pairs=[(item,v["R001"]["label"],v["R002"]["label"]) for item,v in by_task[task].items() if set(v)=={"R001","R002"}]
        a=[x[1] for x in pairs];b=[x[2] for x in pairs];disagreements=[x for x in pairs if x[1]!=x[2]]
        result={"overlap":len(pairs),"agreements":len(pairs)-len(disagreements),"disagreements":len(disagreements),
                "observed_agreement":(len(pairs)-len(disagreements))/len(pairs) if pairs else None,
                "cohens_kappa":cohens_kappa(a,b),"krippendorff_alpha_nominal":krippendorff_alpha(rows_for_alpha[task])}
        if task=="seasonality":
            ordinal=[x for x in pairs if x[1] in ORDINAL and x[2] in ORDINAL]
            result["weighted_cohens_kappa_ordinal"]=cohens_kappa([x[1] for x in ordinal],[x[2] for x in ordinal],weighted=True)
            result["weighted_kappa_excluded_insufficient_evidence_pairs"]=len(pairs)-len(ordinal)
            result["krippendorff_alpha_ordinal"]=krippendorff_alpha([r for r in rows_for_alpha[task] if r["decision"] in ORDINAL],ordinal=True)
        report["tasks"][task]=result
        context=template(task);out=[]
        for item,r1,r2 in disagreements:
            meta=context[item]
            base={"review_item_id":item,"review_dataset_version":VERSION,"r001_label":r1,"r002_label":r2,
                  "adjudicator_id":"","adjudicated_label":"","adjudication_timestamp":"","evidence_reviewed":"","rationale":""}
            if task=="mapping":base.update(attraction_id=meta["attraction_id"],attraction_name=meta["attraction_name"],district=meta["district"],proposed_activity=meta["proposed_activity"],description=meta.get("description",""),source_references=meta.get("source_references",""))
            else:base.update(attraction_id=meta["attraction_id"],attraction_name=meta["attraction_name"],activity_type_id=meta["activity_type_id"],activity=meta["activity"],calendar_month=meta["calendar_month"],district=meta["district"],historical_reference_period=meta["historical_reference_period"],rainfall_mean_mm=meta["rainfall_mean_mm"],rainfall_cv=meta["rainfall_cv"],temperature_mean_c=meta["temperature_mean_c"],relative_humidity_mean_pct=meta["relative_humidity_mean_pct"],wind_speed_mean_ms=meta["wind_speed_mean_ms"],solar_radiation_mean_mj=meta["solar_radiation_mean_mj"],climate_source_type=meta["climate_source_type"])
            out.append(base)
        fields=list(out[0]) if out else (["review_item_id","review_dataset_version","r001_label","r002_label","adjudicator_id","adjudicated_label","adjudication_timestamp","evidence_reviewed","rationale"])
        write_csv(OUT/f"adjudication_{task}.csv",out,fields)
    REPORT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))
if __name__=="__main__":main()
