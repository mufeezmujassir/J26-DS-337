#!/usr/bin/env python3
"""Operator-managed, two-reviewer workflow for the prospective blind package."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Json

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation.label_ingestion import load_labels
from app.climate.evaluation.review_workflow import assign_items,completion_status,finalize_assignment
from app.climate.evaluation.reviewer_agreement import agreement_from_submissions,krippendorff_alpha
from app.climate.evaluation.prospective import DATASET_VERSION
from app.climate.evaluation.label_validation import SEASONALITY_LABELS

OUT=ROOT/"data"/"evaluation"/"stage12_4g"
TEMPLATE=OUT/"prospective_reviewer_template.csv"


def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def template_ids():
    with TEMPLATE.open(encoding="utf-8-sig",newline="") as f:return [r["review_item_id"] for r in csv.DictReader(f)]


def assign(conn,args):
    with conn.cursor() as cur:
        cur.execute("SELECT count(DISTINCT reviewer_id) FROM climate_review_assignments WHERE review_dataset_version=%s",(DATASET_VERSION,))
        count=cur.fetchone()[0]
        cur.execute("SELECT 1 FROM climate_review_assignments WHERE review_dataset_version=%s AND reviewer_id=%s LIMIT 1",(DATASET_VERSION,args.reviewer))
        known=cur.fetchone() is not None
    if count>=2 and not known:raise ValueError("prospective protocol permits exactly two reviewer identities")
    requested=assign_items(conn,args.reviewer,"seasonality",template_ids(),version=DATASET_VERSION);conn.commit()
    return {"status":"ASSIGNED","requested_items":requested,"state":completion_status(conn,args.reviewer,"seasonality",version=DATASET_VERSION)}


def import_reviews(conn,args):
    labels=load_labels(Path(args.csv),"seasonality",TEMPLATE,DATASET_VERSION)
    if any(r["reviewer_id"]!=args.reviewer for r in labels):raise ValueError("CSV contains another reviewer_id")
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM climate_review_assignments WHERE review_dataset_version=%s AND reviewer_id=%s LIMIT 1",(DATASET_VERSION,args.reviewer));state=cur.fetchone()
        if not state:raise ValueError("reviewer has no prospective assignment")
        if state[0]=="FINALIZED":raise ValueError("prospective assignment is finalized; corrections require explicit research authorization")
        for row in labels:
            cur.execute("SELECT 1 FROM climate_review_assignments WHERE review_dataset_version=%s AND task_type='seasonality' AND review_item_id=%s AND reviewer_id=%s",(DATASET_VERSION,row["review_item_id"],args.reviewer))
            if not cur.fetchone():raise ValueError(f"unassigned item: {row['review_item_id']}")
            evidence={"evidence_reviewed":row["evidence_reviewed"],"confidence":row["confidence"],"expertise":row.get("reviewer_expertise",""),"notes":row.get("notes","")}
            stamp=datetime.fromisoformat(row["review_timestamp"].replace("Z","+00:00"))
            cur.execute("""INSERT INTO climate_reviewer_label_submissions(dataset_version,task_type,review_item_id,reviewer_id,label,reviewed_at,evidence_json)
              VALUES(%s,'seasonality',%s,%s,%s,%s,%s) ON CONFLICT(dataset_version,task_type,review_item_id,reviewer_id) DO NOTHING""",
              (DATASET_VERSION,row["review_item_id"],args.reviewer,row["decision"],stamp,Json(evidence)))
        cur.execute("UPDATE climate_review_assignments SET status='IN_PROGRESS' WHERE review_dataset_version=%s AND reviewer_id=%s AND status='ASSIGNED'",(DATASET_VERSION,args.reviewer))
    conn.commit();return {"status":"IMPORTED","valid_rows":len(labels),"state":completion_status(conn,args.reviewer,"seasonality",version=DATASET_VERSION)}


def completeness(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT reviewer_id FROM climate_review_assignments WHERE review_dataset_version=%s ORDER BY 1",(DATASET_VERSION,));reviewers=[r[0] for r in cur.fetchall()]
        cur.execute("SELECT review_item_id,reviewer_id,label FROM climate_reviewer_label_submissions WHERE dataset_version=%s ORDER BY 1,2",(DATASET_VERSION,));raw=cur.fetchall()
        cur.execute("SELECT count(*) FROM climate_adjudicated_labels WHERE dataset_version=%s",(DATASET_VERSION,));adjudicated=cur.fetchone()[0]
    rows=[{"review_item_id":x,"reviewer_id":r,"decision":label} for x,r,label in raw]
    by_item=defaultdict(list)
    for row in rows:by_item[row["review_item_id"]].append(row["decision"])
    disagreements=sum(len(v)==2 and len(set(v))>1 for v in by_item.values())
    return {"status":"PENDING_INDEPENDENT_EVIDENCE" if len(raw)<1728 or adjudicated<disagreements else "REVIEWS_AND_ADJUDICATION_COMPLETE",
        "reviewers":reviewers,"reviewer_count":len(reviewers),"judgments":len(raw),"expected_judgments":1728,
        "items_with_two_reviews":sum(len(v)==2 for v in by_item.values()),"disagreements":disagreements,
        "adjudications":adjudicated,"missing_adjudications":max(0,disagreements-adjudicated),
        "agreement":agreement_from_submissions(rows,weighted=True),"krippendorff_alpha_ordinal":krippendorff_alpha(rows,ordinal=True)}


def adjudication_template(conn,args):
    with conn.cursor() as cur:
        cur.execute("SELECT review_item_id,reviewer_id,label FROM climate_reviewer_label_submissions WHERE dataset_version=%s ORDER BY 1,2",(DATASET_VERSION,));raw=cur.fetchall()
    by=defaultdict(list)
    for item,reviewer,label in raw:by[item].append((reviewer,label))
    rows=[]
    for item,values in sorted(by.items()):
        if len(values)==2 and values[0][1]!=values[1][1]:
            rows.append({"review_item_id":item,"review_dataset_version":DATASET_VERSION,
                "reviewer_1_id":values[0][0],"reviewer_1_decision":values[0][1],
                "reviewer_2_id":values[1][0],"reviewer_2_decision":values[1][1],
                "adjudicator_id":"","adjudicated_at":"","final_decision":"","evidence_reviewed":"","rationale":""})
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else ["review_item_id","review_dataset_version","reviewer_1_id","reviewer_1_decision","reviewer_2_id","reviewer_2_decision","adjudicator_id","adjudicated_at","final_decision","evidence_reviewed","rationale"]
    with path.open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)
    return {"status":"ADJUDICATION_TEMPLATE_CREATED","disagreements":len(rows),"path":str(path)}


def import_adjudication(conn,args):
    with Path(args.csv).open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    if len(rows)!=len({r["review_item_id"] for r in rows}):raise ValueError("duplicate adjudication item")
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT reviewer_id FROM climate_reviewer_label_submissions WHERE dataset_version=%s",(DATASET_VERSION,));reviewers={r[0] for r in cur.fetchall()}
        for row in rows:
            required=[k for k in ("review_item_id","adjudicator_id","adjudicated_at","final_decision","evidence_reviewed","rationale") if not row.get(k,"").strip()]
            if required:raise ValueError(f"{row.get('review_item_id')}: missing {','.join(required)}")
            if row["adjudicator_id"] in reviewers:raise ValueError("adjudicator must be independent of both reviewers")
            label=row["final_decision"].upper()
            if label not in SEASONALITY_LABELS:raise ValueError("invalid final decision")
            stamp=datetime.fromisoformat(row["adjudicated_at"].replace("Z","+00:00"))
            cur.execute("SELECT count(DISTINCT label) FROM climate_reviewer_label_submissions WHERE dataset_version=%s AND review_item_id=%s",(DATASET_VERSION,row["review_item_id"]))
            if cur.fetchone()[0]!=2:raise ValueError(f"{row['review_item_id']} is not a verified disagreement")
            cur.execute("""INSERT INTO climate_adjudicated_labels(dataset_version,task_type,review_item_id,adjudicator_id,label,adjudicated_at,rationale,evidence_json)
              VALUES(%s,'seasonality',%s,%s,%s,%s,%s,%s) ON CONFLICT(dataset_version,task_type,review_item_id) DO NOTHING""",
              (DATASET_VERSION,row["review_item_id"],row["adjudicator_id"],label,stamp,row["rationale"],Json({"evidence_reviewed":row["evidence_reviewed"]})))
    conn.commit();return {"status":"ADJUDICATIONS_IMPORTED","rows":len(rows),"completeness":completeness(conn)}


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    for cmd in ("assign","import","status","finalize"):
        q=sub.add_parser(cmd);q.add_argument("--reviewer",required=True)
        if cmd=="import":q.add_argument("--csv",required=True)
    sub.add_parser("completeness")
    q=sub.add_parser("prepare-adjudication");q.add_argument("--output",default=str(OUT/"prospective_adjudication_completed.csv"))
    q=sub.add_parser("import-adjudication");q.add_argument("--csv",required=True)
    args=p.parse_args()
    with psycopg.connect(dsn()) as conn:
        if args.command=="assign":result=assign(conn,args)
        elif args.command=="import":result=import_reviews(conn,args)
        elif args.command=="status":result=completion_status(conn,args.reviewer,"seasonality",version=DATASET_VERSION)
        elif args.command=="finalize":result=finalize_assignment(conn,args.reviewer,"seasonality",version=DATASET_VERSION);conn.commit()
        elif args.command=="completeness":result=completeness(conn)
        elif args.command=="prepare-adjudication":result=adjudication_template(conn,args)
        else:result=import_adjudication(conn,args)
    print(json.dumps(result,indent=2,default=str))


if __name__=="__main__":main()
