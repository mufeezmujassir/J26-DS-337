from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from psycopg.types.json import Json

REVIEW_VERSION = "stage12_4e2_review_v1"
TASKS = {"mapping", "seasonality"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def assign_items(conn, reviewer_id: str, task_type: str, item_ids: list[str], *, version: str = REVIEW_VERSION) -> int:
    if not reviewer_id.strip() or task_type not in TASKS:
        raise ValueError("valid reviewer_id and task_type are required")
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("duplicate item in assignment request")
    with conn.cursor() as cur:
        for item_id in item_ids:
            cur.execute(
                """INSERT INTO climate_review_assignments
                   (review_dataset_version,task_type,review_item_id,reviewer_id,status,assigned_at,metadata_json)
                   VALUES (%s,%s,%s,%s,'ASSIGNED',%s,%s)
                   ON CONFLICT (review_dataset_version,task_type,review_item_id,reviewer_id) DO NOTHING""",
                (version, task_type, item_id, reviewer_id, utcnow(), Json({"access": "operator_managed_cli"})),
            )
    return len(item_ids)


def completion_status(conn, reviewer_id: str, task_type: str, *, version: str = REVIEW_VERSION) -> dict:
    with conn.cursor() as cur:
        cur.execute("""SELECT a.status, count(*), count(s.id) FROM climate_review_assignments a
            LEFT JOIN climate_reviewer_label_submissions s
              ON s.dataset_version=a.review_dataset_version AND s.task_type=a.task_type
             AND s.review_item_id=a.review_item_id AND s.reviewer_id=a.reviewer_id
            WHERE a.review_dataset_version=%s AND a.task_type=%s AND a.reviewer_id=%s
            GROUP BY a.status""", (version, task_type, reviewer_id))
        rows = cur.fetchall()
    status_counts = Counter()
    submitted = 0
    for status, assignment_count, submission_count in rows:
        status_counts[status] += assignment_count
        submitted += submission_count
    assigned = sum(status_counts.values())
    return {"reviewer_id": reviewer_id, "task_type": task_type, "assigned": assigned,
            "submitted": submitted, "remaining": assigned - submitted,
            "complete": assigned > 0 and assigned == submitted,
            "assignment_statuses": dict(status_counts)}


def finalize_assignment(conn, reviewer_id: str, task_type: str, *, version: str = REVIEW_VERSION) -> dict:
    state = completion_status(conn, reviewer_id, task_type, version=version)
    if not state["complete"]:
        raise ValueError("cannot finalize an incomplete or empty assignment")
    with conn.cursor() as cur:
        cur.execute("""UPDATE climate_review_assignments SET status='FINALIZED', finalized_at=%s
            WHERE review_dataset_version=%s AND task_type=%s AND reviewer_id=%s""",
            (utcnow(), version, task_type, reviewer_id))
    finalized_state = completion_status(conn, reviewer_id, task_type, version=version)
    finalized_state["finalized"] = True
    return finalized_state
