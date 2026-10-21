from __future__ import annotations
from datetime import datetime

MAPPING_LABELS={"SUPPORTED","UNSUPPORTED","UNCERTAIN","INSUFFICIENT_EVIDENCE"}
SEASONALITY_LABELS={"VERY_FAVORABLE","FAVORABLE","NEUTRAL","UNFAVORABLE","VERY_UNFAVORABLE","INSUFFICIENT_EVIDENCE"}
CONFIDENCE_LABELS={"LOW","MEDIUM","HIGH"}

def validate_label(row:dict,task_type:str,valid_items:set[str],dataset_version:str)->dict:
    required=("review_item_id","reviewer_id","review_timestamp","decision","evidence_reviewed","confidence")
    missing=[k for k in required if not str(row.get(k,"" )).strip()]
    if missing: raise ValueError(f"missing required fields: {','.join(missing)}")
    if row["review_item_id"] not in valid_items: raise ValueError("unknown review item")
    if row.get("dataset_version",dataset_version)!=dataset_version: raise ValueError("dataset version mismatch")
    allowed=MAPPING_LABELS if task_type=="mapping" else SEASONALITY_LABELS
    decision=str(row["decision"]).upper()
    if decision not in allowed: raise ValueError("invalid label")
    confidence=str(row["confidence"]).upper()
    if confidence not in CONFIDENCE_LABELS: raise ValueError("invalid confidence")
    try: datetime.fromisoformat(str(row["review_timestamp"]).replace("Z","+00:00"))
    except ValueError as exc: raise ValueError("invalid review timestamp") from exc
    value=dict(row);value["decision"]=decision;value["confidence"]=confidence;return value

def validate_independence(rows:list[dict])->None:
    seen=set()
    for row in rows:
        key=(row["review_item_id"],row["reviewer_id"])
        if key in seen: raise ValueError("duplicate reviewer submission")
        seen.add(key)
