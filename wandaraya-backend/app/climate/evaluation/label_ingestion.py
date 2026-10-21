from __future__ import annotations
import csv
from pathlib import Path
from .label_validation import validate_independence,validate_label

def load_labels(path:Path,task_type:str,template_path:Path,dataset_version:str)->list[dict]:
    # Excel commonly writes UTF-8 CSVs with a BOM. utf-8-sig accepts both BOM and
    # non-BOM files while keeping the first header exactly "review_item_id".
    with template_path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or "review_item_id" not in reader.fieldnames:
            raise ValueError(f"template is missing review_item_id; headers={reader.fieldnames}")
        template={r["review_item_id"]:r for r in reader}
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or "review_item_id" not in reader.fieldnames:
            raise ValueError(f"review CSV is missing review_item_id; headers={reader.fieldnames}")
        rows=list(reader)
    completed=[r for r in rows if str(r.get("decision","")).strip()]
    validated=[validate_label(r,task_type,set(template),dataset_version) for r in completed]
    identity_fields=("attraction_id",) if task_type=="mapping" else ("attraction_id","activity_type_id","calendar_month")
    for row in validated:
        expected=template[row["review_item_id"]]
        if row.get("review_dataset_version",dataset_version)!=dataset_version:
            raise ValueError(f"review dataset version mismatch for {row['review_item_id']}")
        for field in identity_fields:
            if str(row.get(field,""))!=str(expected.get(field,"")):
                raise ValueError(f"{field} mismatch for {row['review_item_id']}")
    validate_independence(validated)
    return validated

def label_availability(paths:list[Path])->dict:
    counts={}
    for path in paths:
        if not path.exists(): counts[path.name]=0;continue
        with path.open(encoding="utf-8",newline="") as f: counts[path.name]=sum(bool(str(r.get("decision","")).strip()) for r in csv.DictReader(f))
    total=sum(counts.values())
    return {"status":"LABELS_AVAILABLE" if total else "HUMAN_LABELS_PENDING","completed_labels":total,"files":counts}
