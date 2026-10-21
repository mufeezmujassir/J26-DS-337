from __future__ import annotations
import math

RELEVANCE={"VERY_UNFAVORABLE":0,"UNFAVORABLE":1,"NEUTRAL":2,"FAVORABLE":3,"VERY_FAVORABLE":4}
def _complete(pred,rel):
    common=[x for x in pred if x in rel and rel[x] is not None]
    if not common:return []
    return common
def ndcg(pred:list[int],rel:dict[int,float],k:int)->float|None:
    judged=_complete(pred,rel)
    if len(judged)<k:return None
    dcg=sum((2**rel[m]-1)/math.log2(i+2) for i,m in enumerate(judged[:k]))
    ideal=sorted((rel[m] for m in judged),reverse=True)[:k]
    idcg=sum((2**v-1)/math.log2(i+2) for i,v in enumerate(ideal))
    return 0.0 if idcg==0 else dcg/idcg
def spearman(a:list[int],b:list[int])->float|None:
    if len(a)!=len(b) or len(a)<2:return None
    n=len(a);return 1-6*sum((x-y)**2 for x,y in zip(a,b))/(n*(n*n-1))
def kendall(a:list[int],b:list[int])->float|None:
    if len(a)!=len(b) or len(a)<2:return None
    c=d=0
    for i in range(len(a)):
        for j in range(i+1,len(a)):
            v=(a[i]-a[j])*(b[i]-b[j]);c+=v>0;d+=v<0
    return (c-d)/(c+d) if c+d else None
def top_k_overlap(a:list[int],b:list[int],k:int=3)->float:return len(set(a[:k])&set(b[:k]))/k
def reciprocal_rank(pred:list[int],relevant:set[int])->float|None:
    if not relevant:return None
    for i,item in enumerate(pred,1):
        if item in relevant:return 1/i
    return 0.0
