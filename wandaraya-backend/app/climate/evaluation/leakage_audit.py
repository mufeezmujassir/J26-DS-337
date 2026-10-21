from __future__ import annotations
import csv,hashlib,json
from pathlib import Path
def verify_checksums(root:Path,checksum_path:Path)->dict:
    payload=json.loads(checksum_path.read_text(encoding="utf-8"));results={}
    for name,expected in payload["files"].items():results[name]={"expected":expected,"actual":hashlib.sha256((root/name).read_bytes()).hexdigest()};results[name]["match"]=results[name]["actual"]==expected
    return {"all_match":all(x["match"] for x in results.values()),"files":results}
def blind_template_exposure(path:Path)->dict:
    with path.open(encoding="utf-8",newline="") as f:fields=csv.DictReader(f).fieldnames or []
    prohibited=[x for x in fields if any(k in x.lower() for k in ("score","rank","prediction","eligibility","evidence_tier"))]
    return {"safe":not prohibited,"prohibited_fields":prohibited}
