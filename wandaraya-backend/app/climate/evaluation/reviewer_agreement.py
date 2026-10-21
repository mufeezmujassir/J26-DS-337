from __future__ import annotations
from collections import Counter,defaultdict

ORDINAL={"VERY_UNFAVORABLE":0,"UNFAVORABLE":1,"NEUTRAL":2,"FAVORABLE":3,"VERY_FAVORABLE":4}

def cohens_kappa(a:list[str],b:list[str],weighted:bool=False)->dict:
    if len(a)!=len(b) or not a: return {"status":"INSUFFICIENT_OVERLAP","n":0,"kappa":None}
    labels=sorted(set(a)|set(b));n=len(a)
    if weighted and all(x in ORDINAL for x in labels):
        scale=max(1,len(ORDINAL)-1); w=lambda x,y:((ORDINAL[x]-ORDINAL[y])/scale)**2
        observed=sum(w(x,y) for x,y in zip(a,b))/n
        ca,cb=Counter(a),Counter(b);expected=sum((ca[x]/n)*(cb[y]/n)*w(x,y) for x in labels for y in labels)
        k=None if expected==0 else 1-observed/expected
    else:
        observed=sum(x==y for x,y in zip(a,b))/n
        ca,cb=Counter(a),Counter(b);expected=sum(ca[x]*cb[x] for x in labels)/(n*n)
        k=None if expected==1 else (observed-expected)/(1-expected)
    return {"status":"COMPUTED","n":n,"observed_agreement":sum(x==y for x,y in zip(a,b))/n,"kappa":k}

def agreement_from_submissions(rows:list[dict],weighted:bool=False)->dict:
    by_reviewer=defaultdict(dict)
    for r in rows: by_reviewer[r["reviewer_id"]][r["review_item_id"]]=r["decision"]
    reviewers=sorted(by_reviewer)
    if len(reviewers)!=2:return {"status":"REQUIRES_EXACTLY_TWO_REVIEWERS","reviewer_count":len(reviewers)}
    common=sorted(set(by_reviewer[reviewers[0]])&set(by_reviewer[reviewers[1]]))
    return cohens_kappa([by_reviewer[reviewers[0]][i] for i in common],[by_reviewer[reviewers[1]][i] for i in common],weighted)

def adjudication_template(rows:list[dict])->list[dict]:
    by_item=defaultdict(list)
    for r in rows:by_item[r["review_item_id"]].append(r)
    return [{"review_item_id":k,"original_judgments":[{"reviewer_id":x["reviewer_id"],"decision":x["decision"]} for x in v],"adjudicator_id":"","adjudicated_label":"","adjudicated_at":"","rationale":""} for k,v in sorted(by_item.items()) if len({x["decision"] for x in v})>1]

def krippendorff_alpha(rows:list[dict],ordinal:bool=False)->dict:
    """Krippendorff alpha for any number of reviewers; missing item ratings are allowed."""
    by_item=defaultdict(list)
    for r in rows: by_item[r["review_item_id"]].append(r["decision"])
    usable=[v for v in by_item.values() if len(v)>1]
    values=[x for v in usable for x in v]
    if not usable or len(set(values))<2:
        return {"status":"INSUFFICIENT_OVERLAP","items":len(usable),"alpha":None}
    def delta(a,b):
        if ordinal and a in ORDINAL and b in ORDINAL:return ((ORDINAL[a]-ORDINAL[b])/4)**2
        return float(a!=b)
    do_num=do_den=0.0
    for ratings in usable:
        n=len(ratings);do_num+=sum(delta(a,b) for i,a in enumerate(ratings) for j,b in enumerate(ratings) if i!=j)/(n-1);do_den+=n
    observed=do_num/do_den
    counts=Counter(values);n=len(values)
    expected=sum(counts[a]*counts[b]*delta(a,b) for a in counts for b in counts)/(n*(n-1))
    return {"status":"COMPUTED" if expected else "INSUFFICIENT_VARIATION","items":len(usable),
            "alpha":None if not expected else 1-observed/expected}
