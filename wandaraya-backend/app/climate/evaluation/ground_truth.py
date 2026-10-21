from __future__ import annotations

import hashlib, json
from collections import defaultdict
from datetime import datetime, timezone

from psycopg.types.json import Json

GROUND_TRUTH_VERSION="stage12_4e2_ground_truth_v1"
ORDINAL={"VERY_UNFAVORABLE":0,"UNFAVORABLE":1,"NEUTRAL":2,"FAVORABLE":3,"VERY_FAVORABLE":4}


def construct_ground_truth(conn, review_version:str, item_metadata:dict[str,dict], *, persist:bool=False)->dict:
    """Build labels only from genuine finalized reviews; disagreements require adjudication."""
    with conn.cursor() as cur:
        cur.execute("""SELECT s.review_item_id,s.reviewer_id,s.label,s.evidence_json,a.status
            FROM climate_reviewer_label_submissions s JOIN climate_review_assignments a
              ON a.review_dataset_version=s.dataset_version AND a.task_type=s.task_type
             AND a.review_item_id=s.review_item_id AND a.reviewer_id=s.reviewer_id
            WHERE s.dataset_version=%s AND s.task_type='seasonality'""",(review_version,))
        submissions=cur.fetchall()
        cur.execute("SELECT review_item_id,label,adjudicator_id,rationale FROM climate_adjudicated_labels WHERE dataset_version=%s AND task_type='seasonality'",(review_version,))
        adjudicated={r[0]:r[1:] for r in cur.fetchall()}
    by_item=defaultdict(list)
    for item,reviewer,label,evidence,status in submissions:
        if status=="FINALIZED":by_item[item].append({"reviewer_id":reviewer,"label":label,"evidence":evidence})
    records=[];unresolved=[]
    for item,ratings in sorted(by_item.items()):
        if len(ratings)<2:continue
        labels={r["label"] for r in ratings}
        selected=next(iter(labels)) if len(labels)==1 else adjudicated.get(item,(None,))[0]
        if selected not in ORDINAL and selected!="INSUFFICIENT_EVIDENCE":
            unresolved.append(item);continue
        meta=item_metadata[item]
        records.append({"evaluation_query_id":f"{meta['attraction_id']}:{meta['activity_type_id']}","review_item_id":item,
            "attraction_id":int(meta["attraction_id"]),"activity_id":int(meta["activity_type_id"]),"calendar_month":int(meta["calendar_month"]),
            "relevance_grade":ORDINAL.get(selected),"reviewer_count":len(ratings),"adjudication_status":"CONSENSUS" if len(labels)==1 else "ADJUDICATED",
            "evidence_provenance":[r["evidence"] for r in ratings],"dataset_version":GROUND_TRUTH_VERSION,
            "review_sampling_version":review_version,"label_completeness_status":"COMPLETE" if selected in ORDINAL else "INSUFFICIENT_EVIDENCE"})
    complete_queries={r["evaluation_query_id"] for r in records if sum(x["evaluation_query_id"]==r["evaluation_query_id"] for x in records)==12}
    records=[r for r in records if r["evaluation_query_id"] in complete_queries]
    rankable_queries={q for q in complete_queries if all(r["relevance_grade"] is not None for r in records if r["evaluation_query_id"]==q)}
    manifest={"dataset_version":GROUND_TRUTH_VERSION,"review_sampling_version":review_version,"records":len(records),
        "complete_queries":len(complete_queries),"fully_rankable_queries":len(rankable_queries),
        "insufficient_evidence_records":sum(r["relevance_grade"] is None for r in records),
        "unresolved_disagreements":len(unresolved),"created_at":datetime.now(timezone.utc).isoformat()}
    manifest["records_sha256"]=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    if persist and records:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO climate_ground_truth_dataset_versions(dataset_version,review_sampling_version,status,manifest_json,created_at)
                VALUES(%s,%s,'VERIFIED',%s,%s) ON CONFLICT(dataset_version) DO NOTHING""",
                (GROUND_TRUTH_VERSION,review_version,Json(manifest),datetime.now(timezone.utc)))
    return {"status":"CREATED" if records else "PENDING_GENUINE_COMPLETE_REVIEWS","manifest":manifest,"records":records}
