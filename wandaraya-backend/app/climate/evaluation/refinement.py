"""Leakage-aware Stage 12.4F refinement candidates; no production activation."""
from __future__ import annotations
from collections import defaultdict
from statistics import mean

BLEND_GRID=(0.0,0.25,0.5,0.75,1.0)

def candidate_scores(activity:float,district:float,generic:float,cohort:str,coordinate:bool=False)->dict[str,float]:
    confidence={"A":0.75,"B":0.35}.get(cohort,0.0)
    if coordinate:confidence=min(0.85,confidence+0.10)
    conservative_strength=0.25 if cohort=="A" else 0.0
    return {
        "A_activity_aware":activity,
        "B_district_multivariable":district,
        "C_activity_weighting_disabled":generic,
        "D_reduced_activity_weight_strength":0.5*activity+0.5*generic,
        "E_evidence_confidence_aware":confidence*activity+(1-confidence)*generic,
        "F_fixed_calibrated_blend":0.25*activity+0.75*district,
        "G_conservative_adjustment":district+conservative_strength*(activity-generic),
    }

def deterministic_rank(month_scores:dict[int,float])->list[int]:
    return sorted(month_scores,key=lambda m:(-month_scores[m],m))

def grouped_folds(query_clusters:dict[str,str],folds:int=5)->list[set[str]]:
    clusters=sorted(set(query_clusters.values()))
    result=[set() for _ in range(min(folds,len(clusters)))]
    for i,cluster in enumerate(clusters):result[i%len(result)].add(cluster)
    return result

def select_blend_weight(train_queries:list[dict],metric_fn,grid=BLEND_GRID)->float:
    scored=[]
    for weight in grid:
        values=[]
        for q in train_queries:
            order=deterministic_rank({m:weight*q["activity"][m]+(1-weight)*q["district"][m] for m in q["activity"]})
            values.append(metric_fn(order,q["relevance"]))
        scored.append((mean(values),-weight,weight))
    return max(scored)[2]

def grouped_cross_validated_blend(queries:list[dict],metric_fn,folds:int=5)->dict:
    cluster_by_query={q["query_id"]:q["cluster"] for q in queries};split=grouped_folds(cluster_by_query,folds)
    predictions={};selected=[]
    for index,test_clusters in enumerate(split):
        train=[q for q in queries if q["cluster"] not in test_clusters];test=[q for q in queries if q["cluster"] in test_clusters]
        weight=select_blend_weight(train,metric_fn);selected.append({"fold":index+1,"activity_weight":weight,"train_queries":len(train),"test_queries":len(test),"test_clusters":sorted(test_clusters)})
        for q in test:predictions[q["query_id"]]={m:weight*q["activity"][m]+(1-weight)*q["district"][m] for m in q["activity"]}
    return {"predictions":predictions,"folds":selected,"query_count":len(predictions),"leakage_check":len(predictions)==len(queries)}
