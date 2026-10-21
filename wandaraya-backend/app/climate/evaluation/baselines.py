from __future__ import annotations
import hashlib,json

BASELINES={
 "rainfall_only":{"version":"12.4c_v1","inputs":["baseline_a_rainfall_rank"],"definition":"ascending district median monthly rainfall"},
 "district_multivariable":{"version":"12.4c_v1","inputs":["baseline_b_multivar_score"],"definition":"0.45 rainfall + 0.25 temperature + 0.15 humidity + 0.15 solar"},
 "rainfall_risk_adjusted":{"version":"12.4c_v1","inputs":["baseline_c_variability_rank"],"definition":"ascending rainfall mean + 0.5 rainfall standard deviation"},
 "activity_aware":{"version":"12.4d_v1","inputs":["climate_favorability_score"],"definition":"frozen Stage 12.4D activity-specific score"},
}
def configuration_hash(value:dict)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def deterministic_ranks(rows:list[dict],score_key:str,descending:bool=True)->dict[int,int]:
    ordered=sorted(rows,key=lambda r:((-float(r[score_key])) if descending else float(r[score_key]),int(r["calendar_month"])))
    return {int(r["calendar_month"]):i for i,r in enumerate(ordered,1)}
