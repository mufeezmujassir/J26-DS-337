from __future__ import annotations
import random
from statistics import mean
def paired_effect(a:list[float],b:list[float])->dict:
    if len(a)!=len(b) or not a:return {"n":0,"mean_difference":None}
    d=[x-y for x,y in zip(a,b)];return {"n":len(d),"mean_difference":mean(d),"mean_absolute_difference":mean(abs(x) for x in d)}
def cluster_bootstrap(values:dict[str,list[float]],seed:int=12401,iterations:int=500)->dict:
    keys=sorted(values)
    if not keys:return {"status":"NO_DATA"}
    rng=random.Random(seed);est=[]
    for _ in range(iterations):
        sample=[rng.choice(keys) for _ in keys];flat=[v for k in sample for v in values[k]];est.append(mean(flat))
    est.sort();return {"status":"COMPUTED","clusters":len(keys),"iterations":iterations,"seed":seed,"mean":mean(est),"ci95":[est[int(.025*iterations)],est[min(iterations-1,int(.975*iterations))]]}
