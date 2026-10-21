from __future__ import annotations
from .baselines import configuration_hash

FEATURES=("rainfall_sub_index","rainfall_reliability","temperature_comfort","humidity_comfort","solar_context","wind_context")
def build_ablation_configurations()->list[dict]:
    configs=[
      {"id":"full_activity_aware","version":"12.4e1_v1","removed":[],"renormalize":False,"available":True},
      {"id":"without_rainfall_reliability","version":"12.4e1_v1","removed":["rainfall_reliability"],"renormalize":True,"available":True},
      {"id":"without_temperature","version":"12.4e1_v1","removed":["temperature_comfort"],"renormalize":True,"available":True},
      {"id":"without_humidity","version":"12.4e1_v1","removed":["humidity_comfort"],"renormalize":True,"available":True},
      {"id":"without_solar","version":"12.4e1_v1","removed":["solar_context"],"renormalize":True,"available":True},
      {"id":"without_wind","version":"12.4e1_v1","removed":["wind_context"],"renormalize":True,"available":False,"unavailable_reason":"No Stage 12.4D activity profile assigns wind a non-zero weight."},
      {"id":"without_activity_weighting","version":"12.4e1_v1","removed":[],"renormalize":True,"available":True,"generic_weights":{"rainfall_sub_index":.45,"temperature_comfort":.25,"humidity_comfort":.15,"solar_context":.15}},
      {"id":"district_only_fallback","version":"12.4e1_v1","removed":[],"renormalize":False,"available":True,"policy":"use district feature inputs for every pair"},
      {"id":"rainfall_only_simplified","version":"12.4e1_v1","removed":["rainfall_reliability","temperature_comfort","humidity_comfort","solar_context","wind_context"],"renormalize":True,"available":True},
    ]
    for c in configs:c["configuration_hash"]=configuration_hash(c)
    return configs
def weighted_score(row:dict,weights:dict,removed:list[str])->float|None:
    active={k:v for k,v in weights.items() if k not in removed and v>0 and row.get(k) not in (None,"")}
    if not active:return None
    total=sum(active.values());return round(sum(float(row[k])*w for k,w in active.items())/total,6)
