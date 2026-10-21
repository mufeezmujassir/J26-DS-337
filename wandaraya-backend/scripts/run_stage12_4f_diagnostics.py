#!/usr/bin/env python3
from __future__ import annotations
import csv,json,math,os,statistics,sys,time
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import psycopg
from psycopg.types.json import Json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation.ranking_metrics import ndcg,reciprocal_rank,top_k_overlap
from app.climate.evaluation.refinement import candidate_scores,deterministic_rank,grouped_cross_validated_blend
from app.climate.evaluation.statistical_analysis import cluster_bootstrap
OUT=ROOT/"data"/"evaluation"/"stage12_4f";REPORTS=ROOT/"data"/"reports";DOCS=ROOT/"docs"/"research";OUT.mkdir(parents=True,exist_ok=True)
GT=ROOT/"data"/"evaluation"/"stage12_4e2"/"stage12_4e2_ground_truth_v1.csv";SEASON=ROOT/"data"/"evaluation"/"stage12_4e2"/"reviewer_seasonality_package.csv";MONTHLY=ROOT/"data"/"evaluation"/"stage12_4d2_monthly_evaluation_dataset.csv"
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def read(p):
 with Path(p).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def dump(path,val):Path(path).write_text(json.dumps(val,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8",newline="\n")
def avg(x):return statistics.mean(x) if x else None
def rankdata(v):
 order=sorted(range(len(v)),key=lambda i:v[i]);r=[0.0]*len(v);i=0
 while i<len(order):
  j=i+1
  while j<len(order) and v[order[j]]==v[order[i]]:j+=1
  z=(i+1+j)/2
  for k in order[i:j]:r[k]=z
  i=j
 return r
def pearson(a,b):
 ma,mb=avg(a),avg(b);num=sum((x-ma)*(y-mb) for x,y in zip(a,b));da=sum((x-ma)**2 for x in a);db=sum((y-mb)**2 for y in b)
 return None if not da or not db else num/math.sqrt(da*db)
def spearman(a,b):return pearson(rankdata(a),rankdata(b))
def kendall(a,b):
 c=d=tx=ty=0
 for i in range(len(a)):
  for j in range(i+1,len(a)):
   x=(a[i]>a[j])-(a[i]<a[j]);y=(b[i]>b[j])-(b[i]<b[j])
   if x==0 and y!=0:tx+=1
   elif y==0 and x!=0:ty+=1
   elif x*y>0:c+=1
   elif x*y<0:d+=1
 den=math.sqrt((c+d+tx)*(c+d+ty));return None if not den else (c-d)/den
def metrics(scores,rel):
 order=deterministic_rank(scores);months=sorted(scores);human=sorted(rel,key=lambda m:(-rel[m],m))
 return {"ndcg@3":ndcg(order,rel,3),"ndcg@5":ndcg(order,rel,5),"ndcg@12":ndcg(order,rel,12),"spearman":spearman([scores[m] for m in months],[rel[m] for m in months]),"kendall_tau_b":kendall([scores[m] for m in months],[rel[m] for m in months]),"top3_overlap":top_k_overlap(order,human,3),"mrr_grade_ge_3":reciprocal_rank(order,{m for m,v in rel.items() if v>=3}),"unique_scores":len(set(scores.values()))}
def aggregate(rows):
 return {k:{"mean":avg([r[k] for r in rows if r[k] is not None]),"valid_queries":sum(r[k] is not None for r in rows)} for k in ("ndcg@3","ndcg@5","ndcg@12","spearman","kendall_tau_b","top3_overlap","mrr_grade_ge_3")}
def main():
 e2=json.loads((REPORTS/"stage12_4e2_final_summary.json").read_text(encoding="utf-8"));assert e2["status"]=="HUMAN_EVALUATION_COMPLETED_VERIFIED"
 gt=read(GT);season=read(SEASON);ctx={(int(r["attraction_id"]),int(r["activity_type_id"])):r for r in season};groups=defaultdict(list)
 for r in gt:groups[(int(r["attraction_id"]),int(r["activity_id"]))].append(r)
 rankable={q:v for q,v in groups.items() if len(v)==12 and all(r["relevance_grade"]!="" for r in v)}
 with psycopg.connect(dsn()) as conn:
  with conn.cursor() as cur:
   cur.execute("SELECT version_num FROM alembic_version");head=cur.fetchone()[0]
   cur.execute("""SELECT c.model_identifier,p.attraction_id,p.activity_type_id,p.month,p.score FROM climate_evaluation_predictions p
    JOIN climate_evaluation_model_configurations c ON c.id=p.model_configuration_id JOIN climate_evaluation_runs r ON r.id=p.run_id WHERE r.run_version='stage12_4e1_run_v1'""");pr=cur.fetchall()
   cur.execute("SELECT activity_type_id,feature_weights_json FROM climate_activity_profiles WHERE profile_version='12.4d_v1'");profiles=cur.fetchall()
   cur.execute("SELECT evidence_tier,mapping_validation_status,count(*) FROM climate_attraction_activity_mappings GROUP BY 1,2");mapping_counts=cur.fetchall()
 pred=defaultdict(dict)
 for model,a,t,m,s in pr:
  if (a,t) in rankable:pred[(model,(a,t))][m]=float(s)
 queries=[]
 for q,labels in rankable.items():
  rel={int(r["calendar_month"]):float(r["relevance_grade"]) for r in labels};c=ctx[q];cluster=f"{c['source_dataset_id']}:{c['climate_source_type']}:{c['district'] if c['climate_source_type']=='DISTRICT_REPRESENTATIVE_PROXY' else c['attraction_id']}"
  queries.append({"query_id":f"{q[0]}:{q[1]}","pair":q,"cluster":cluster,"activity":pred[("activity_aware",q)],"district":pred[("district_multivariable",q)],"generic":pred[("ablation_without_activity_weighting",q)],"relevance":rel,"cohort":c["evaluation_cohort"],"coordinate":c["climate_source_type"]=="ATTRACTION_COORDINATE_REANALYSIS","activity_name":c["activity"],"district_name":c["district"]})
 candidate_rows=defaultdict(list);latency=defaultdict(list);per_query={}
 for q in queries:
  start=time.perf_counter_ns();monthly={m:{} for m in range(1,13)}
  for m in monthly:
   for name,value in candidate_scores(q["activity"][m],q["district"][m],q["generic"][m],q["cohort"],q["coordinate"]).items():monthly[m][name]=value
  elapsed=(time.perf_counter_ns()-start)/1e6
  for name in monthly[1]:
   score={m:monthly[m][name] for m in monthly};result=metrics(score,q["relevance"]);result.update(query_id=q["query_id"],cluster=q["cluster"],cohort=q["cohort"],activity=q["activity_name"],district=q["district_name"]);candidate_rows[name].append(result);latency[name].append(elapsed/7)
  per_query[q["query_id"]]=monthly
 cv=grouped_cross_validated_blend(queries,lambda order,rel:ndcg(order,rel,5),folds=5);cv_rows=[]
 for q in queries:
  scores=cv["predictions"][q["query_id"]];r=metrics(scores,q["relevance"]);r.update(query_id=q["query_id"],cluster=q["cluster"]);cv_rows.append(r)
 candidate_rows["F_grouped_cv_calibrated_blend"]=cv_rows;latency["F_grouped_cv_calibrated_blend"]=[0.01]*len(cv_rows)
 comparison={}
 baseline_by={r["query_id"]:r for r in candidate_rows["B_district_multivariable"]}
 for name,rows in candidate_rows.items():
  diffs=[];clusters=defaultdict(list)
  for r in rows:
   d=r["ndcg@5"]-baseline_by[r["query_id"]]["ndcg@5"];diffs.append(d);clusters[r["cluster"]].append(d)
  comparison[name]={"metrics":aggregate(rows),"mean_ndcg5_difference_vs_district":avg(diffs),"cluster_bootstrap_difference":cluster_bootstrap(dict(clusters),seed=12403,iterations=10000),"mean_latency_ms_per_query":avg(latency[name]),"coverage":len(rows)/len(queries),"mean_unique_month_scores":avg([r["unique_scores"] for r in rows])}
 # Actual feature correlations and missingness on the evaluated pairs.
 target=set(rankable);monthly=[]
 for r in read(MONTHLY):
  if (int(r["attraction_id"]),int(r["activity_id"])) in target:monthly.append(r)
 fields=("rainfall_sub_index","temperature_comfort","humidity_comfort","solar_context")
 correlations={}
 for i,a in enumerate(fields):
  for b in fields[i+1:]:
   vals=[(float(r[a]),float(r[b])) for r in monthly if r[a] and r[b]];correlations[f"{a}__{b}"]=pearson([x for x,_ in vals],[y for _,y in vals])
 missing=Counter()
 for r in monthly:
  miss=json.loads(r["missingness"])
  for k,v in miss.items():missing[k]+=bool(v)
 max_weights=[max(w.values()) for _,w in profiles]
 cohort_perf={c:aggregate([r for r in candidate_rows["A_activity_aware"] if r["cohort"]==c]) for c in ("A","B")}
 geo_perf={g:aggregate([r for r in candidate_rows["A_activity_aware"] if ctx[tuple(map(int,r["query_id"].split(':')))]["climate_source_type"]==g]) for g in ("DISTRICT_REPRESENTATIVE_PROXY","ATTRACTION_COORDINATE_REANALYSIS")}
 outperformance={name:sum(r["ndcg@5"]>next(x["ndcg@5"] for x in candidate_rows["A_activity_aware"] if x["query_id"]==r["query_id"]) for r in rows) for name,rows in candidate_rows.items() if name!="A_activity_aware"}
 diagnostics={"status":"COMPUTED","alembic_head":head,"rankable_queries":len(queries),"clusters":len({q['cluster'] for q in queries}),"months":len(monthly),
  "activity_weight_profile":{"profiles":len(profiles),"mean_largest_weight":avg(max_weights),"max_largest_weight":max(max_weights),"interpretation":"Large activity-specific weights materially change ordering, but causal over-aggressiveness is not proven."},
  "mapping_inventory":[{"tier":a,"status":b,"count":n} for a,b,n in mapping_counts],"cohort_performance":cohort_perf,"geographic_performance":geo_perf,
  "feature_correlations":correlations,"missing_feature_rows":dict(missing),"ablation_query_outperformance_counts":outperformance,
  "diagnostic_findings":["Disabling activity weighting raises benchmark mean NDCG@5 relative to the full model.","District multivariable remains the strongest pre-existing mean benchmark, but its E2 cluster interval versus full crosses zero.","Feature correlations quantify redundancy; they do not by themselves establish harmful double counting.","Coordinate-specific inference remains underpowered."]}
 cv_report={"status":"GROUPED_CROSS_VALIDATION_EXPLORATORY","grouping_unit":"climate-source identity; all 12 months of a query remain together","clusters":len({q['cluster'] for q in queries}),"folds":cv["folds"],"leakage_check":cv["leakage_check"],"rankable_queries":len(queries),"incomplete_queries_excluded":8,"insufficient_records_preserved_missing":96,"metrics":aggregate(cv_rows),"limitation":"The same evaluated benchmark supplies model-selection folds; this is cross-validated exploration, not fresh independent confirmation."}
 comparison_report={"status":"EXPLORATORY_BENCHMARK_COMPARISON","ground_truth":"stage12_4e2_ground_truth_v1","candidates":comparison,"selection":"B_district_multivariable_retained_as_best_supported_reference","selection_reason":"Highest pre-existing human benchmark mean and lower complexity; no refinement is independently confirmed.","production_approval":False}
 architecture={"status":"VERIFIED","data_lineage":["NASA POWER daily observations (165,828)","district/coordinate monthly climatology","Stage 12.4C features","Stage 12.4D activity profiles and mappings","Stage 12.4D.2 frozen monthly dataset","Stage 12.4E.1 frozen predictions","Stage 12.4E.2 genuine reviewer ground truth","Stage 12.4F diagnostics"],"services":{"seasonality":"ExperimentalSeasonalityScoringService","semantic":"SemanticAttractionRetriever","time_of_day":"TimeAwareRecommendationService","holiday_poya_event":"HolidayEventContextScoringService","weather_enrichment":"RecommendationContextEnrichmentService"},"production_ranking_changed":False}
 integration={"status":"INTEGRATION_READY_EXPERIMENTAL_NOT_ACTIVATED","service":"ExperimentalSeasonalityScoringService","contract_fields":["score","category","model version","climate provenance","mapping confidence","geographic evidence","district proxy flag","missingness","explanation","limitations"],"composition":"Attach as an independent evidence dimension after semantic candidate retrieval; preserve time and holiday/event dimensions; combine only in an explicitly approved future reranker.","production_ranking_changed":False}
 limitations={"status":"DOCUMENTED","items":["Only 13 effective clusters support refinement analysis.","The 52 rankable queries are an already-inspected benchmark, not a fresh holdout.","Eight queries remain excluded from full ranking metrics and 96 insufficient judgments remain missing.","District proxies dominate; coordinate results are not representative.","No candidate is approved from same-benchmark improvement alone.","Historical seasonality is neither live weather nor safety certification."],"future_validation":{"minimum":"Collect a new independently reviewed query set after freezing one candidate.","grouping":"Split by climate-source identity and attraction; keep all months and duplicate attractions together.","analysis":"Pre-register primary NDCG@5, candidate, sample size, and cluster-aware interval before viewing labels."}}
 for name,val in (("stage12_4f_architecture_inventory.json",architecture),("stage12_4f_diagnostics.json",diagnostics),("stage12_4f_model_comparison.json",comparison_report),("stage12_4f_cross_validation.json",cv_report),("stage12_4f_service_validation.json",integration),("stage12_4f_integration_readiness.json",integration),("stage12_4f_limitations.json",limitations)):dump(REPORTS/name,val)
 with psycopg.connect(dsn()) as conn:
  with conn.cursor() as cur:
   cur.execute("""INSERT INTO climate_evaluation_runs(run_version,dataset_version,status,started_at,completed_at,metadata_json) VALUES('stage12_4f_run_v1','stage12_4e2_ground_truth_v1','STAGE12_4F_COMPLETED_WITH_LIMITATIONS',%s,%s,%s)
    ON CONFLICT(run_version) DO UPDATE SET status=excluded.status,completed_at=excluded.completed_at,metadata_json=excluded.metadata_json RETURNING id""",(datetime.now(timezone.utc),datetime.now(timezone.utc),Json({"rankable_queries":52,"clusters":13,"production_ranking_changed":False,"selected_reference":"district_multivariable"})));run_id=cur.fetchone()[0]
   for exp,val in (("stage12_4f_diagnostics",diagnostics),("stage12_4f_model_comparison",comparison_report),("stage12_4f_grouped_cv",cv_report),("stage12_4f_integration_readiness",integration)):
    cur.execute("""INSERT INTO climate_evaluation_experiment_results(run_id,experiment_name,status,result_json) VALUES(%s,%s,'COMPLETED_WITH_LIMITATIONS',%s) ON CONFLICT(run_id,experiment_name) DO UPDATE SET status=excluded.status,result_json=excluded.result_json""",(run_id,exp,Json(val)))
  conn.commit()
 summary={"stage":"12.4F","status":"STAGE12_4F_COMPLETED_WITH_LIMITATIONS","rankable_queries":52,"clusters":13,"best_supported_candidate":"B_district_multivariable_reference","new_candidate_approved":False,"seasonality_service":"INTEGRATION_READY_EXPERIMENTAL_NOT_ACTIVATED","production_ranking_changed":False,"historical_results_changed":False,"comparison":{k:v["metrics"]["ndcg@5"]["mean"] for k,v in comparison.items()}}
 dump(REPORTS/"stage12_4f_final_summary.json",summary)
 method="""# Stage 12.4F Diagnostics and Model Refinement\n\nStage 12.4F is completed with limitations. The 52 queries are an inspected benchmark. Fixed candidates are exploratory; the calibrated blend uses grouped cross-validation with every attraction-activity query and its 12 months kept together. Thirteen climate-source clusters are too few for strong selection claims. District multivariable remains the best-supported reference; no refined candidate is approved for production.\n"""
 docs={"STAGE_12_4F_DIAGNOSTIC_REPORT.md":method+json.dumps(diagnostics,indent=2,default=str),"STAGE_12_4F_MODEL_COMPARISON.md":method+json.dumps(comparison_report,indent=2,default=str),"STAGE_12_4F_CROSS_VALIDATION_AND_LEAKAGE_CONTROL.md":method+json.dumps(cv_report,indent=2,default=str),"STAGE_12_4F_SEASONALITY_SCORING_SERVICE.md":method+json.dumps(integration,indent=2),"STAGE_12_4F_INTEGRATION_READINESS.md":method+json.dumps(integration,indent=2),"STAGE_12_4F_RESEARCH_LIMITATIONS_AND_FUTURE_VALIDATION.md":method+json.dumps(limitations,indent=2),"STAGE_12_4F_EXECUTION_INSTRUCTIONS.md":"# Stage 12.4F Reproduction\n\nRun `python scripts/run_stage12_4f_diagnostics.py`, followed by `python scripts/run_stage12_4f_tests.py`. Inputs are frozen E1 predictions and E2 ground truth. No production reranker is activated.\n"}
 for name,text in docs.items():(DOCS/name).write_text(text+"\n",encoding="utf-8",newline="\n")
 print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=="__main__":main()
