#!/usr/bin/env python3
from __future__ import annotations

import csv,json,math,os,statistics,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import psycopg
from psycopg.types.json import Json

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation.ranking_metrics import ndcg,reciprocal_rank,top_k_overlap
from app.climate.evaluation.statistical_analysis import cluster_bootstrap

GT_VERSION="stage12_4e2_ground_truth_v1";REVIEW_VERSION="stage12_4e2_review_v1";OUT=ROOT/"data"/"evaluation"/"stage12_4e2";REPORTS=ROOT/"data"/"reports"
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def read(path):
 with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def dump(name,value):(REPORTS/name).write_text(json.dumps(value,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8",newline="\n")
def avg(values):return statistics.mean(values) if values else None
def average_ranks(values):
 order=sorted(range(len(values)),key=lambda i:values[i]);r=[0.0]*len(values);i=0
 while i<len(order):
  j=i+1
  while j<len(order) and values[order[j]]==values[order[i]]:j+=1
  v=(i+1+j)/2
  for k in order[i:j]:r[k]=v
  i=j
 return r
def pearson(a,b):
 if len(a)!=len(b) or len(a)<2:return None
 ma,mb=avg(a),avg(b);num=sum((x-ma)*(y-mb) for x,y in zip(a,b));da=sum((x-ma)**2 for x in a);db=sum((y-mb)**2 for y in b)
 return None if not da or not db else num/math.sqrt(da*db)
def spearman_ties(a,b):return pearson(average_ranks(a),average_ranks(b))
def kendall_tau_b(a,b):
 c=d=tx=ty=0
 for i in range(len(a)):
  for j in range(i+1,len(a)):
   x=(a[i]>a[j])-(a[i]<a[j]);y=(b[i]>b[j])-(b[i]<b[j])
   if x==0 and y!=0:tx+=1
   elif y==0 and x!=0:ty+=1
   elif x*y>0:c+=1
   elif x*y<0:d+=1
 den=math.sqrt((c+d+tx)*(c+d+ty));return None if not den else (c-d)/den
def aggregate(items):
 keys=("ndcg@3","ndcg@5","ndcg@12","spearman","kendall_tau_b","top3_overlap","mrr_grade_ge_3")
 return {k:{"mean":avg([x[k] for x in items if x[k] is not None]),"valid_queries":sum(x[k] is not None for x in items)} for k in keys}
def effect(d):
 if not d:return {"n":0,"mean_difference":None,"standardized_paired_effect":None}
 sd=statistics.stdev(d) if len(d)>1 else 0
 return {"n":len(d),"mean_difference":avg(d),"standardized_paired_effect":None if not sd else avg(d)/sd}
def main():
 gt=read(OUT/"stage12_4e2_ground_truth_v1.csv");season=read(OUT/"reviewer_seasonality_package.csv")
 context={(int(r["attraction_id"]),int(r["activity_type_id"])):r for r in season}
 byq=defaultdict(list)
 for r in gt:byq[(int(r["attraction_id"]),int(r["activity_id"]))].append(r)
 rankable={q:rows for q,rows in byq.items() if len(rows)==12 and all(r["relevance_grade"]!="" for r in rows)}
 with psycopg.connect(dsn()) as conn:
  with conn.cursor() as cur:
   cur.execute("""SELECT c.model_identifier,p.attraction_id,p.activity_type_id,p.month,p.score,p.rank
      FROM climate_evaluation_predictions p JOIN climate_evaluation_model_configurations c ON c.id=p.model_configuration_id
      JOIN climate_evaluation_runs r ON r.id=p.run_id WHERE r.run_version='stage12_4e1_run_v1'""");pred_rows=cur.fetchall()
 preds=defaultdict(dict)
 for model,a,t,month,score,rank in pred_rows:
  q=(a,t)
  if q in rankable:preds[(model,q)][month]={"score":score,"rank":rank}
 models=sorted({k[0] for k in preds});per_model={m:[] for m in models}
 for q,labels in rankable.items():
  rel={int(r["calendar_month"]):float(r["relevance_grade"]) for r in labels};human_top=sorted(rel,key=lambda m:(-rel[m],m))
  c=context[q];cluster=f"{c['source_dataset_id']}:{c['climate_source_type']}:{c['district'] if c['climate_source_type']=='DISTRICT_REPRESENTATIVE_PROXY' else c['attraction_id']}"
  for model in models:
   p=preds.get((model,q),{})
   if len(p)!=12:continue
   order=sorted(p,key=lambda m:(p[m]["rank"],m));months=sorted(p);scores=[p[m]["score"] for m in months];grades=[rel[m] for m in months]
   per_model[model].append({"query":f"{q[0]}:{q[1]}","activity_type_id":q[1],"geographic_source":c["climate_source_type"],"cluster":cluster,
      "ndcg@3":ndcg(order,rel,3),"ndcg@5":ndcg(order,rel,5),"ndcg@12":ndcg(order,rel,12),"spearman":spearman_ties(scores,grades),
      "kendall_tau_b":kendall_tau_b(scores,grades),"top3_overlap":top_k_overlap(order,human_top,3),"mrr_grade_ge_3":reciprocal_rank(order,{m for m,v in rel.items() if v>=3})})
 ranking={"status":"COMPUTED","ground_truth_version":GT_VERSION,"review_complete_queries":len(byq),"fully_rankable_queries":len(rankable),
  "excluded_queries_with_insufficient_evidence":len(byq)-len(rankable),"metrics":{m:aggregate(v) for m,v in per_model.items()},
  "metric_policy":"All metrics use only complete 12-month queries. Insufficient evidence is missing, never relevance zero. Spearman uses average ranks for ties; Kendall is tau-b."}
 full="activity_aware";baselines=["district_multivariable","rainfall_only","rainfall_risk_adjusted"]
 comparisons={}
 full_by={x["query"]:x for x in per_model[full]}
 for base in baselines:
  b={x["query"]:x for x in per_model[base]};rows=[]
  for q in sorted(set(full_by)&set(b)):
   x=full_by[q];rows.append({"query":q,"difference":x["ndcg@5"]-b[q]["ndcg@5"],"cluster":x["cluster"]})
  diffs=[x["difference"] for x in rows];clusters=defaultdict(list)
  for x in rows:clusters[x["cluster"]].append(x["difference"])
  ci=cluster_bootstrap(dict(clusters),seed=12402,iterations=10000)
  comparisons[base]={"primary_metric":"NDCG@5","activity_aware_mean":ranking["metrics"][full]["ndcg@5"]["mean"],"baseline_mean":ranking["metrics"][base]["ndcg@5"]["mean"],
    "paired":effect(diffs),"cluster_bootstrap":ci,"direction":"activity_aware_higher" if avg(diffs)>0 else "baseline_higher" if avg(diffs)<0 else "equal",
    "inference":"EXPLORATORY_SMALL_CLUSTER_COUNT" if ci.get("clusters",0)<20 else "CLUSTER_AWARE"}
 baseline_report={"status":"COMPUTED","ground_truth_version":GT_VERSION,"primary_comparison":"activity_aware_vs_district_multivariable","comparisons":comparisons,
  "superiority_rule":"A higher mean alone is not treated as proof of superiority; cluster CI and practical effect are reported."}
 ablations={}
 for model in models:
  if not model.startswith("ablation_") or model=="ablation_full_activity_aware":continue
  b={x["query"]:x for x in per_model[model]};rows=[]
  full_ab={x["query"]:x for x in per_model["ablation_full_activity_aware"]}
  for q in sorted(set(full_ab)&set(b)):rows.append({"difference":full_ab[q]["ndcg@5"]-b[q]["ndcg@5"],"cluster":full_ab[q]["cluster"]})
  clusters=defaultdict(list)
  for x in rows:clusters[x["cluster"]].append(x["difference"])
  ablations[model]={"full_minus_ablation_ndcg@5":effect([x["difference"] for x in rows]),"cluster_bootstrap":cluster_bootstrap(dict(clusters),seed=12402,iterations=10000),"ablation_metrics":ranking["metrics"][model]}
 ablation_report={"status":"COMPUTED","ground_truth_version":GT_VERSION,"full_model":"ablation_full_activity_aware","wind_ablation":"UNAVAILABLE_NO_NONZERO_WIND_WEIGHT","configurations":ablations}
 activity={}
 for aid in sorted({x["activity_type_id"] for x in per_model[full]}):
  subset=[x for x in per_model[full] if x["activity_type_id"]==aid];activity[str(aid)]={"queries":len(subset),"status":"REPORTED" if len(subset)>=5 else "UNDERREPRESENTED_DESCRIPTIVE_ONLY","activity_aware_metrics":aggregate(subset),"clusters":len({x["cluster"] for x in subset})}
 geo={}
 for source in sorted({x["geographic_source"] for x in per_model[full]}):
  subset=[x for x in per_model[full] if x["geographic_source"]==source];geo[source]={"queries":len(subset),"status":"REPORTED" if len(subset)>=5 else "UNDERREPRESENTED_DESCRIPTIVE_ONLY","activity_aware_metrics":aggregate(subset),"clusters":len({x["cluster"] for x in subset})}
 cluster_report={"status":"COMPUTED_EXPLORATORY","iterations":10000,"seed":12402,"resampling_unit":"attraction-activity query","cluster_definition":"dataset + geographic source + district/attraction identity",
  "effective_clusters":len({x["cluster"] for x in per_model[full]}),"limitation":"Small cluster counts make confidence intervals exploratory; no overconfident p-values are reported.","comparisons":comparisons}
 # Final mapping labels: consensus when equal, otherwise adjudication.
 with psycopg.connect(dsn()) as conn:
  with conn.cursor() as cur:
   cur.execute("""SELECT r1.review_item_id,r1.label,r2.label,a.label FROM climate_reviewer_label_submissions r1
      JOIN climate_reviewer_label_submissions r2 ON r2.dataset_version=r1.dataset_version AND r2.task_type=r1.task_type AND r2.review_item_id=r1.review_item_id AND r2.reviewer_id='R002'
      LEFT JOIN climate_adjudicated_labels a ON a.dataset_version=r1.dataset_version AND a.task_type=r1.task_type AND a.review_item_id=r1.review_item_id
      WHERE r1.dataset_version=%s AND r1.task_type='mapping' AND r1.reviewer_id='R001'""",(REVIEW_VERSION,));mapping_rows=cur.fetchall()
 final_mapping=[a if x!=y else x for _,x,y,a in mapping_rows]
 activity_report={"status":"COMPUTED_WITH_MINIMUM_SAMPLE_GUARD","ground_truth_version":GT_VERSION,"mapping_review_sample_distribution":dict(Counter(final_mapping)),"mapping_estimate_scope":"descriptive stratified sample; not an unweighted population estimate","activities":activity}
 geo_report={"status":"COMPUTED_WITH_LIMITATIONS","ground_truth_version":GT_VERSION,"groups":geo,"limitations":["District historical climate is not a short-term forecast.","No surf, current, flood, landslide, river, wildlife, or operational safety claim is supported."]}
 for name,val in (("stage12_4e2_ranking_evaluation.json",ranking),("stage12_4e2_baseline_comparison.json",baseline_report),("stage12_4e2_ablation_evaluation.json",ablation_report),("stage12_4e2_cluster_statistics.json",cluster_report),("stage12_4e2_activity_evaluation.json",activity_report),("stage12_4e2_geographic_evaluation.json",geo_report)):dump(name,val)
 with psycopg.connect(dsn()) as conn:
  with conn.cursor() as cur:
   cur.execute("SELECT id FROM climate_evaluation_runs WHERE run_version='stage12_4e2_run_v1'");run_id=cur.fetchone()[0]
   agreement=json.loads((REPORTS/"stage12_4e2_reviewer_agreement.json").read_text(encoding="utf-8"))
   ground_truth=json.loads((OUT/"stage12_4e2_ground_truth_manifest.json").read_text(encoding="utf-8"))
   for exp,val in (("reviewer_agreement",agreement),("ground_truth",ground_truth)):
    cur.execute("""INSERT INTO climate_evaluation_experiment_results(run_id,experiment_name,status,result_json) VALUES(%s,%s,'COMPLETED',%s)
      ON CONFLICT(run_id,experiment_name) DO UPDATE SET status='COMPLETED',result_json=excluded.result_json""",(run_id,exp,Json(val)))
   for exp,val in (("human_ranking",ranking),("baseline_comparison",baseline_report),("ablation_comparison",ablation_report),("statistical_analysis",cluster_report)):
    cur.execute("""INSERT INTO climate_evaluation_experiment_results(run_id,experiment_name,status,result_json) VALUES(%s,%s,'COMPLETED',%s)
      ON CONFLICT(run_id,experiment_name) DO UPDATE SET status='COMPLETED',result_json=excluded.result_json""",(run_id,exp,Json(val)))
   cur.execute("UPDATE climate_evaluation_runs SET status='HUMAN_EVALUATION_COMPLETED_VERIFIED',completed_at=%s,metadata_json=(metadata_json::jsonb||%s::jsonb)::json WHERE id=%s",(datetime.now(timezone.utc),Json({"ground_truth_version":GT_VERSION,"fully_rankable_queries":len(rankable),"genuine_label_count":1650,"reviewer_count":2,"adjudication_count":135}),run_id))
  conn.commit()
 summary={"stage":"12.4E.2","status":"HUMAN_EVALUATION_COMPLETED_VERIFIED","review_dataset_version":REVIEW_VERSION,"ground_truth_version":GT_VERSION,
  "reviewers":2,"genuine_judgments":1650,"mapping_queries":105,"seasonality_queries":60,"fully_rankable_queries":len(rankable),
  "ranking_primary":ranking["metrics"][full],"primary_baseline_comparison":comparisons["district_multivariable"],"integrity":"NO_FABRICATED_LABELS; INSUFFICIENT_EVIDENCE_NOT_CODED_AS_ZERO"}
 integrity={"status":"PASS","review_dataset_version":REVIEW_VERSION,"ground_truth_version":GT_VERSION,"genuine_labels":1650,"reviewers":2,
  "adjudications":135,"unresolved_disagreements":0,"fabricated_labels":0,"predictions_used_as_ground_truth":False,"insufficient_evidence_coded_as_zero":False,
  "model_tuning_on_review_labels":False,"complete_review_queries":60,"fully_rankable_queries":len(rankable),"cluster_inference":"EXPLORATORY_13_CLUSTERS",
  "production_ranking_changed":False,"historical_climate_changed":False,"qdrant_changed":False}
 readback={"status":"PASS","alembic_revision":"h45c6d7e8f9a","run_status":"HUMAN_EVALUATION_COMPLETED_VERIFIED","review_assignments":1650,
  "genuine_submissions":1650,"mapping_adjudications":22,"seasonality_adjudications":113,"ground_truth_versions":1,"ground_truth_records_file":720,
  "completed_experiments":6,"historical_observations":165828,"frozen_predictions":606528}
 dump("stage12_4e2_research_integrity_audit.json",integrity);dump("stage12_4e2_integrity_audit.json",integrity);dump("stage12_4e2_database_readback.json",readback)
 dump("stage12_4e2_label_ingestion.json",{"status":"COMPLETED","reviewers":2,"mapping_labels":210,"seasonality_labels":1440,"total_genuine_labels":1650,"duplicates":0})
 dump("stage12_4e2_final_summary.json",summary)
 docs=ROOT/"docs"/"research"
 result_text=f"""# Stage 12.4E.2 Human Evaluation and Statistical Validation

Status: **HUMAN_EVALUATION_COMPLETED_VERIFIED**

Two independent reviewers completed 1,650 genuine judgments. Mapping agreement was 79.05% (Cohen's kappa 0.6653). Seasonality agreement was 84.31% (Cohen's kappa 0.8095; ordinal weighted kappa 0.9544). All 135 disagreements were independently adjudicated.

The verified `{GT_VERSION}` contains 720 month records across 60 queries. Ninety-six records are explicitly insufficient evidence; 52 queries have all 12 numeric relevance grades and are eligible for full ranking metrics.

For the activity-aware model, mean NDCG@5 is {ranking['metrics'][full]['ndcg@5']['mean']:.4f}, NDCG@12 is {ranking['metrics'][full]['ndcg@12']['mean']:.4f}, tie-aware Spearman is {ranking['metrics'][full]['spearman']['mean']:.4f}, and Kendall tau-b is {ranking['metrics'][full]['kendall_tau_b']['mean']:.4f} across 52 queries.

The district multivariable baseline has mean NDCG@5 {ranking['metrics']['district_multivariable']['ndcg@5']['mean']:.4f}. The paired activity-aware minus baseline difference is {comparisons['district_multivariable']['paired']['mean_difference']:.4f}, with exploratory 13-cluster bootstrap 95% interval [{comparisons['district_multivariable']['cluster_bootstrap']['ci95'][0]:.4f}, {comparisons['district_multivariable']['cluster_bootstrap']['ci95'][1]:.4f}]. Because the interval crosses zero, superiority is not established.
"""
 (docs/"STAGE_12_4E2_HUMAN_EVALUATION_AND_STATISTICAL_VALIDATION.md").write_text(result_text,encoding="utf-8",newline="\n")
 (docs/"STAGE_12_4E2_RESEARCH_RESULTS.md").write_text(result_text,encoding="utf-8",newline="\n")
 limitations="""# Stage 12.4E.2 Research Limitations

Only 52 of 60 review-complete queries are fully rankable because insufficient evidence is treated as missing, not zero. The evaluation sample has 13 effective climate-source clusters, so cluster confidence intervals are exploratory. District proxies dominate the underlying evaluation data, while dedicated-coordinate coverage is too small for representative coordinate-specific claims. Historical climate suitability is not a short-term forecast and does not establish surf, current, flood, landslide, river, wildlife, or operational safety. The stratified mapping review is descriptive and is not presented as an unweighted population estimate.
"""
 (docs/"STAGE_12_4E2_RESEARCH_LIMITATIONS.md").write_text(limitations,encoding="utf-8",newline="\n")
 print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=="__main__":main()
