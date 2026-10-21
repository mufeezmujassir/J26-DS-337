#!/usr/bin/env python3
"""Operator-only CSV workflow for Stage 12.4E.2 human reviews."""
from __future__ import annotations

import argparse, csv, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Json

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation.label_ingestion import load_labels
from app.climate.evaluation.review_workflow import REVIEW_VERSION,assign_items,completion_status,finalize_assignment
from app.climate.evaluation.label_validation import MAPPING_LABELS,SEASONALITY_LABELS

OUT=ROOT/"data"/"evaluation"/"stage12_4e2"
MAPPING_TEMPLATE=OUT/"reviewer_mapping_package.csv"
if not MAPPING_TEMPLATE.exists():
    MAPPING_TEMPLATE=OUT/"attraction_activity_review.csv"
TEMPLATES={"mapping":MAPPING_TEMPLATE,"seasonality":OUT/"reviewer_seasonality_package.csv"}
def dbdsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def template_ids(task):
    with TEMPLATES[task].open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or "review_item_id" not in reader.fieldnames:
            raise ValueError(f"{TEMPLATES[task]} is missing review_item_id; headers={reader.fieldnames}. Save as UTF-8 CSV or regenerate the package.")
        return [r["review_item_id"] for r in reader]

def do_assign(conn,args):
    count=assign_items(conn,args.reviewer,args.task,template_ids(args.task));conn.commit()
    return {"status":"ASSIGNED","requested_items":count,"state":completion_status(conn,args.reviewer,args.task)}

def do_import(conn,args):
    labels=load_labels(Path(args.csv),args.task,TEMPLATES[args.task],REVIEW_VERSION)
    if any(r["reviewer_id"]!=args.reviewer for r in labels):raise ValueError("CSV contains another reviewer_id")
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM climate_review_assignments WHERE review_dataset_version=%s AND task_type=%s AND reviewer_id=%s LIMIT 1",(REVIEW_VERSION,args.task,args.reviewer))
        state=cur.fetchone()
        if not state:raise ValueError("reviewer has no assignment")
        if state[0]=="FINALIZED":
            cur.execute("""SELECT review_item_id,label,reviewed_at,evidence_json
                FROM climate_reviewer_label_submissions
                WHERE dataset_version=%s AND task_type=%s AND reviewer_id=%s""",
                (REVIEW_VERSION,args.task,args.reviewer))
            persisted={row[0]:row[1:] for row in cur.fetchall()}
            changed=[]
            for row in labels:
                saved=persisted.get(row["review_item_id"])
                submitted_at=datetime.fromisoformat(row["review_timestamp"].replace("Z","+00:00"))
                evidence={"evidence_reviewed":row["evidence_reviewed"],"confidence":row["confidence"],
                          "expertise":row.get("reviewer_expertise",""),"notes":row.get("notes","")}
                if not saved or saved[0]!=row["decision"] or saved[1]!=submitted_at or saved[2]!=evidence:
                    changed.append(row["review_item_id"])
            if len(persisted)==len(labels) and not changed:
                return {"status":"ALREADY_IMPORTED_FINALIZED","valid_rows":len(labels),
                        "changed_rows":0,"message":"Exact finalized submission already exists; no database changes were made.",
                        "state":completion_status(conn,args.reviewer,args.task)}
            preview=",".join(changed[:5])
            raise ValueError(f"assignment is finalized and {len(changed)} row(s) differ ({preview}); use the authorized correction command")
        for row in labels:
            cur.execute("SELECT 1 FROM climate_review_assignments WHERE review_dataset_version=%s AND task_type=%s AND review_item_id=%s AND reviewer_id=%s",(REVIEW_VERSION,args.task,row["review_item_id"],args.reviewer))
            if not cur.fetchone():raise ValueError(f"unassigned item: {row['review_item_id']}")
            cur.execute("""INSERT INTO climate_reviewer_label_submissions
                (dataset_version,task_type,review_item_id,reviewer_id,label,reviewed_at,evidence_json)
                VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(dataset_version,task_type,review_item_id,reviewer_id) DO NOTHING""",
                (REVIEW_VERSION,args.task,row["review_item_id"],args.reviewer,row["decision"],datetime.fromisoformat(row["review_timestamp"].replace("Z","+00:00")),
                 Json({"evidence_reviewed":row["evidence_reviewed"],"confidence":row["confidence"],"expertise":row.get("reviewer_expertise",""),"notes":row.get("notes","")})))
        cur.execute("UPDATE climate_review_assignments SET status='IN_PROGRESS' WHERE review_dataset_version=%s AND task_type=%s AND reviewer_id=%s AND status='ASSIGNED'",(REVIEW_VERSION,args.task,args.reviewer))
    conn.commit();return {"status":"IMPORTED","valid_rows":len(labels),"state":completion_status(conn,args.reviewer,args.task)}

def do_finalize(conn,args):
    result=finalize_assignment(conn,args.reviewer,args.task);conn.commit();return result

def do_correct(conn,args):
    allowed=MAPPING_LABELS if args.task=="mapping" else SEASONALITY_LABELS;new=args.label.upper()
    if new not in allowed or not args.authorized_by.strip() or not args.reason.strip():raise ValueError("valid label, authorized_by, and reason are required")
    with conn.cursor() as cur:
        cur.execute("""SELECT s.id,s.label FROM climate_reviewer_label_submissions s JOIN climate_review_assignments a
            ON a.review_dataset_version=s.dataset_version AND a.task_type=s.task_type AND a.review_item_id=s.review_item_id AND a.reviewer_id=s.reviewer_id
            WHERE s.dataset_version=%s AND s.task_type=%s AND s.review_item_id=%s AND s.reviewer_id=%s AND a.status='FINALIZED'""",
            (REVIEW_VERSION,args.task,args.item,args.reviewer));row=cur.fetchone()
        if not row:raise ValueError("a finalized submission was not found")
        cur.execute("INSERT INTO climate_reviewer_submission_corrections(submission_id,prior_label,revised_label,authorized_by,reason,corrected_at) VALUES(%s,%s,%s,%s,%s,%s)",
            (row[0],row[1],new,args.authorized_by,args.reason,datetime.now(timezone.utc)))
        cur.execute("UPDATE climate_reviewer_label_submissions SET label=%s WHERE id=%s",(new,row[0]))
    conn.commit();return {"status":"CORRECTED","item":args.item,"prior_label":row[1],"revised_label":new}

def do_export(conn,args):
    with conn.cursor() as cur:
        cur.execute("SELECT review_item_id,reviewer_id,label,reviewed_at,evidence_json FROM climate_reviewer_label_submissions WHERE dataset_version=%s AND task_type=%s ORDER BY reviewer_id,review_item_id",(REVIEW_VERSION,args.task));rows=cur.fetchall()
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f,lineterminator="\n");w.writerow(["review_item_id","reviewer_id","decision","review_timestamp","evidence_json"]);w.writerows(rows)
    return {"status":"EXPORTED","rows":len(rows),"path":str(path)}

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    for cmd in ("assign","import","status","finalize"):
        q=sub.add_parser(cmd);q.add_argument("--reviewer",required=True);q.add_argument("--task",choices=sorted(TEMPLATES),required=True)
        if cmd=="import":q.add_argument("--csv",required=True)
    q=sub.add_parser("correct");q.add_argument("--reviewer",required=True);q.add_argument("--task",choices=sorted(TEMPLATES),required=True);q.add_argument("--item",required=True);q.add_argument("--label",required=True);q.add_argument("--authorized-by",required=True);q.add_argument("--reason",required=True)
    q=sub.add_parser("export");q.add_argument("--task",choices=sorted(TEMPLATES),required=True);q.add_argument("--output",required=True)
    args=p.parse_args()
    with psycopg.connect(dbdsn()) as conn:
        if args.command=="assign":result=do_assign(conn,args)
        elif args.command=="import":result=do_import(conn,args)
        elif args.command=="status":result=completion_status(conn,args.reviewer,args.task)
        elif args.command=="finalize":result=do_finalize(conn,args)
        elif args.command=="correct":result=do_correct(conn,args)
        else:result=do_export(conn,args)
    print(json.dumps(result,indent=2,default=str))
if __name__=="__main__":main()
