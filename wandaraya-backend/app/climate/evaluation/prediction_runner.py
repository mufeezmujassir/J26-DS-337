from __future__ import annotations
from collections import defaultdict
from .baselines import deterministic_ranks
def rank_predictions(rows:list[dict])->list[dict]:
    groups=defaultdict(list)
    for r in rows:groups[(r["attraction_id"],r["activity_id"],r["model_identifier"])].append(r)
    out=[]
    for _,items in sorted(groups.items()):
        ranks=deterministic_ranks(items,"computed_score",True)
        for r in items:r=dict(r);r["monthly_rank"]=ranks[int(r["calendar_month"])];out.append(r)
    return sorted(out,key=lambda r:(r["model_identifier"],r["attraction_id"],r["activity_id"],r["calendar_month"]))
