#!/usr/bin/env python3
from __future__ import annotations

import csv, hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Json

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation.ground_truth import construct_ground_truth,GROUND_TRUTH_VERSION
from app.climate.evaluation.label_validation import MAPPING_LABELS,SEASONALITY_LABELS

VERSION="stage12_4e2_review_v1";OUT=ROOT/"data"/"evaluation"/"stage12_4e2";REPORTS=ROOT/"data"/"reports"
FILES={"mapping":OUT/"adjudication_mapping.csv","seasonality":OUT/"adjudication_seasonality.csv"}
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def read(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def dump(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8",newline="\n")
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def validate(conn,task,rows):
    required=("review_item_id","adjudicator_id","adjudicated_label","adjudication_timestamp","evidence_reviewed","rationale")
    allowed=MAPPING_LABELS if task=="mapping" else SEASONALITY_LABELS
    if len(rows)!=len({r["review_item_id"] for r in rows}):raise ValueError(f"duplicate {task} adjudication item")
    with conn.cursor() as cur:
        cur.execute("""SELECT r1.review_item_id FROM climate_reviewer_label_submissions r1
            JOIN climate_reviewer_label_submissions r2 ON r2.dataset_version=r1.dataset_version AND r2.task_type=r1.task_type
             AND r2.review_item_id=r1.review_item_id AND r2.reviewer_id='R002'
            JOIN climate_review_assignments a1 ON a1.review_dataset_version=r1.dataset_version AND a1.task_type=r1.task_type AND a1.review_item_id=r1.review_item_id AND a1.reviewer_id=r1.reviewer_id
            JOIN climate_review_assignments a2 ON a2.review_dataset_version=r2.dataset_version AND a2.task_type=r2.task_type AND a2.review_item_id=r2.review_item_id AND a2.reviewer_id=r2.reviewer_id
            WHERE r1.dataset_version=%s AND r1.task_type=%s AND r1.reviewer_id='R001' AND r1.label<>r2.label
              AND a1.status='FINALIZED' AND a2.status='FINALIZED'""",(VERSION,task));expected={x[0] for x in cur.fetchall()}
    actual={r["review_item_id"] for r in rows}
    if actual!=expected:raise ValueError(f"{task} disagreement coverage mismatch: missing={len(expected-actual)}, unexpected={len(actual-expected)}")
    output=[]
    for row in rows:
        missing=[f for f in required if not str(row.get(f,"")).strip()]
        if missing:raise ValueError(f"{row.get('review_item_id')}: missing {','.join(missing)}")
        if row["adjudicator_id"] in {"R001","R002"}:raise ValueError("adjudicator must be independent of R001 and R002")
        label=row["adjudicated_label"].strip().upper()
        if label not in allowed:raise ValueError(f"{row['review_item_id']}: invalid adjudicated label")
        try:stamp=datetime.fromisoformat(row["adjudication_timestamp"].replace("Z","+00:00"))
        except ValueError as exc:raise ValueError(f"{row['review_item_id']}: invalid timestamp") from exc
        if stamp.tzinfo is None:raise ValueError(f"{row['review_item_id']}: timezone-aware timestamp required")
        output.append((row,label,stamp))
    return output
def main():
    summary={"review_dataset_version":VERSION,"tasks":{},"status":"IMPORTED"}
    with psycopg.connect(dsn()) as conn:
        try:
            for task,path in FILES.items():
                validated=validate(conn,task,read(path));inserted=existing=0
                with conn.cursor() as cur:
                    for row,label,stamp in validated:
                        cur.execute("SELECT adjudicator_id,label,adjudicated_at,rationale,evidence_json FROM climate_adjudicated_labels WHERE dataset_version=%s AND task_type=%s AND review_item_id=%s",(VERSION,task,row["review_item_id"]));prior=cur.fetchone()
                        evidence={"evidence_reviewed":row["evidence_reviewed"],"source_file":path.name}
                        if prior:
                            if prior!=(row["adjudicator_id"],label,stamp,row["rationale"],evidence):raise ValueError(f"final adjudication differs for {row['review_item_id']}; correction migration required")
                            existing+=1;continue
                        cur.execute("""INSERT INTO climate_adjudicated_labels(dataset_version,task_type,review_item_id,adjudicator_id,label,adjudicated_at,rationale,evidence_json)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",(VERSION,task,row["review_item_id"],row["adjudicator_id"],label,stamp,row["rationale"],Json(evidence)));inserted+=1
                summary["tasks"][task]={"validated":len(validated),"inserted":inserted,"already_present":existing}
            conn.commit()
        except Exception:
            conn.rollback();raise
    season={r["review_item_id"]:r for r in read(OUT/"reviewer_seasonality_package.csv")}
    with psycopg.connect(dsn()) as conn:
        result=construct_ground_truth(conn,VERSION,season,persist=True);conn.commit()
    if result["status"]!="CREATED" or result["manifest"]["complete_queries"]!=60 or len(result["records"])!=720:raise RuntimeError("ground truth completeness verification failed")
    fields=["evaluation_query_id","review_item_id","attraction_id","activity_id","calendar_month","relevance_grade","reviewer_count","adjudication_status","evidence_provenance","dataset_version","review_sampling_version","label_completeness_status"]
    gt=OUT/"stage12_4e2_ground_truth_v1.csv"
    with gt.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader()
        for r in result["records"]:
            x=dict(r);x["evidence_provenance"]=json.dumps(x["evidence_provenance"],sort_keys=True,separators=(",",":"),default=str);w.writerow(x)
    result["manifest"]["csv_sha256"]=sha(gt);manifest=OUT/"stage12_4e2_ground_truth_manifest.json";dump(manifest,result["manifest"])
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE climate_ground_truth_dataset_versions SET manifest_json=%s,status='VERIFIED' WHERE dataset_version=%s",(Json(result["manifest"]),GROUND_TRUTH_VERSION))
            cur.execute("SELECT id FROM climate_evaluation_runs WHERE run_version='stage12_4e2_run_v1'");run_id=cur.fetchone()[0]
            for path in (gt,manifest):
                cur.execute("""INSERT INTO climate_evaluation_artifact_references(run_id,artifact_type,path,sha256,created_at)
                    VALUES(%s,'GROUND_TRUTH',%s,%s,%s) ON CONFLICT(run_id,path) DO UPDATE SET sha256=excluded.sha256""",
                    (run_id,str(path.relative_to(ROOT)).replace('\\','/'),sha(path),datetime.now(timezone.utc)))
        conn.commit()
    summary.update({"status":"ADJUDICATIONS_IMPORTED_GROUND_TRUTH_VERIFIED","ground_truth_version":GROUND_TRUTH_VERSION,"ground_truth_records":720,"complete_queries":60,"ground_truth_csv_sha256":sha(gt)})
    dump(REPORTS/"stage12_4e2_ground_truth_status.json",summary);print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=="__main__":main()
