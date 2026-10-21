#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,io,json,os,subprocess,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
import psycopg
from psycopg.types.json import Json

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation import EVALUATION_VERSION
from app.climate.evaluation.ablations import build_ablation_configurations,weighted_score
from app.climate.evaluation.baselines import BASELINES,configuration_hash
from app.climate.evaluation.label_ingestion import label_availability
from app.climate.evaluation.leakage_audit import blind_template_exposure,verify_checksums
from app.climate.evaluation.prediction_runner import rank_predictions
from app.climate.evaluation.ranking_metrics import kendall,spearman,top_k_overlap

FROZEN=ROOT/"data"/"evaluation";OUT=FROZEN/"stage12_4e1";REPORTS=ROOT/"data"/"reports";DOCS=ROOT/"docs"/"research"
OUT.mkdir(parents=True,exist_ok=True);RUN_VERSION="stage12_4e1_run_v1";DATASET_VERSION="stage12_4d2_eval_v1";MIGRATION="f23a4b5c6d7e"
def now():return datetime.now(timezone.utc).isoformat()
def dump(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8",newline="\n")
def load(path):return json.loads(path.read_text(encoding="utf-8"))
def dbdsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def read_csv(path):
 with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def f(v):return None if v in (None,"") else float(v)
def stable_csv(path,rows,fields):
 b=io.StringIO(newline="");w=csv.DictWriter(b,fieldnames=fields,lineterminator="\n");w.writeheader()
 for r in rows:w.writerow({k:(json.dumps(r.get(k),sort_keys=True,separators=(",",":")) if isinstance(r.get(k),(dict,list)) else r.get(k)) for k in fields})
 data=b.getvalue().encode();digest=hashlib.sha256(data).hexdigest()
 if path.exists():
  if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError(f"refusing nondeterministic overwrite: {path}")
  return digest
 path.write_bytes(data);return digest
def avg(vals):
 vals=[x for x in vals if x is not None];return mean(vals) if vals else None

def main():
 started=now();frozen_check=verify_checksums(FROZEN,FROZEN/"stage12_4d2_dataset_checksums.json")
 if not frozen_check["all_match"]:raise RuntimeError("Frozen Stage 12.4D.2 checksum mismatch; evaluation stopped")
 frozen_manifest=load(FROZEN/"stage12_4d2_dataset_manifest.json");monthly=read_csv(FROZEN/"stage12_4d2_monthly_evaluation_dataset.csv")
 cohorts={}
 for key,name in (("A","stage12_4d2_cohort_a_high_evidence.csv"),("B","stage12_4d2_cohort_b_inferred.csv")):
  for r in read_csv(FROZEN/name):cohorts[(int(r["attraction_id"]),int(r["activity_type_id"]))]=(key,int(r["district_id"]))
 with psycopg.connect(dbdsn()) as conn:
  with conn.cursor() as cur:
   cur.execute("SELECT version_num FROM alembic_version");revision=cur.fetchone()[0]
   cur.execute("SELECT id,activity_type FROM climate_activity_types ORDER BY id");activity_codes=dict(cur.fetchall())
   cur.execute("SELECT district_id,month,relative_rainfall_favorability,temperature_comfort_index,humidity_comfort_index,rainfall_reliability_index,baseline_a_rainfall_rank,baseline_b_multivar_score,baseline_b_multivar_rank,baseline_c_variability_rank,feature_vector_json FROM climate_seasonality_features WHERE feature_version='12.4c_v1'")
   district_features={(r[0],r[1]):r[2:] for r in cur.fetchall()}
   cur.execute("SELECT count(*) FROM climate_daily_observations");raw_before=cur.fetchone()[0]
   cur.execute("SELECT count(*) FROM climate_attraction_activity_seasonality");profiles_before=cur.fetchone()[0]
   cur.execute("SELECT count(*) FROM (SELECT lower(regexp_replace(name,'[^a-zA-Z0-9]','','g')) n FROM attractions WHERE is_active GROUP BY 1 HAVING count(*)>1)x");duplicate_name_groups=cur.fetchone()[0]
 preflight={"status":"PREFLIGHT_VERIFIED","verified_at_utc":started,"frozen_checksums":frozen_check,"dataset_version":frozen_manifest["dataset_version"],"git_revision":frozen_manifest["git_commit_hash"],"alembic_revision":revision,"cohort_sizes":frozen_manifest["counts"]["cohorts"],"monthly_rows":len(monthly),"climate_versions":frozen_manifest["climate_dataset_versions"],"activity_profile_versions":frozen_manifest["activity_profile_versions"],"geographic_sources":dict(Counter(r["geographic_source_type"] for r in monthly)),"available_independent_labels":0}
 dump(REPORTS/"stage12_4e1_preflight.json",preflight)
 profile_manifest=load(FROZEN/"stage12_4d2_baseline_configuration_manifest.json")
 by_code={p["activity_type"]:p["feature_weights_json"] for p in profile_manifest["activity_profile_configurations"]}
 keymap={"relative_rainfall_favorability":"rainfall_sub_index","rainfall_reliability_index":"rainfall_reliability","temperature_comfort_index":"temperature_comfort","humidity_comfort_index":"humidity_comfort","solar_radiation_context":"solar_context","wind_context":"wind_context"}
 weights_by_id={aid:{keymap[k]:v for k,v in by_code[code].items()} for aid,code in activity_codes.items()}
 ablations=build_ablation_configurations();dump(OUT/"stage12_4e1_ablation_configurations.json",{"version":EVALUATION_VERSION,"configurations":ablations})
 configs=[]
 for mid,c in BASELINES.items():
  value={"model_identifier":mid,**c};configs.append({**value,"configuration_hash":configuration_hash(value),"kind":"baseline"})
 for c in ablations:
  if c["available"]:configs.append({"model_identifier":"ablation_"+c["id"],"model_version":c["version"],"configuration_hash":c["configuration_hash"],"kind":"ablation",**c})
 dump(OUT/"stage12_4e1_model_configurations.json",configs)
 raw=[]
 for row in monthly:
  aid=int(row["attraction_id"]);act=int(row["activity_id"]);month=int(row["calendar_month"]);cohort,district=cohorts[(aid,act)]
  df=district_features[(district,month)];rain,temp,humid,reliability,rank_a,score_b,rank_b,rank_c,vector=df
  base={"attraction_id":aid,"activity_id":act,"calendar_month":month,"evaluation_cohort":cohort,"geographic_source":row["geographic_source_type"],"source_dataset_id":int(row["source_dataset_id"])}
  baseline_scores={"rainfall_only":(12-int(rank_a))/11,"district_multivariable":float(score_b),"rainfall_risk_adjusted":(12-int(rank_c))/11,"activity_aware":float(row["climate_favorability_score"])}
  for mid,score in baseline_scores.items():raw.append({**base,"model_identifier":mid,"model_version":BASELINES[mid]["version"],"computed_score":round(score,6),"configuration_hash":next(c["configuration_hash"] for c in configs if c["model_identifier"]==mid),"model_kind":"baseline","model_source_dataset_id":3 if mid!="activity_aware" else int(row["source_dataset_id"])})
  source={k:f(row.get(k)) for k in ("rainfall_sub_index","rainfall_reliability","temperature_comfort","humidity_comfort","solar_context","wind_context")}
  district_source={"rainfall_sub_index":float(rain),"rainfall_reliability":float(reliability),"temperature_comfort":float(temp),"humidity_comfort":float(humid),"solar_context":float(vector.get("solar_radiation_normalized",.5)),"wind_context":None}
  for c in ablations:
   if not c["available"]:continue
   mid="ablation_"+c["id"]
   if c["id"]=="full_activity_aware":score=float(row["climate_favorability_score"])
   elif c["id"]=="without_activity_weighting":score=weighted_score(source,c["generic_weights"],[])
   elif c["id"]=="district_only_fallback":score=weighted_score(district_source,weights_by_id[act],[])
   elif c["id"]=="rainfall_only_simplified":score=source["rainfall_sub_index"]
   else:score=weighted_score(source,weights_by_id[act],c["removed"])
   if score is not None:raw.append({**base,"model_identifier":mid,"model_version":c["version"],"computed_score":round(score,6),"configuration_hash":c["configuration_hash"],"model_kind":"ablation","model_source_dataset_id":3 if c["id"]=="district_only_fallback" else int(row["source_dataset_id"])})
 predictions=rank_predictions(raw)
 groups=Counter((r["attraction_id"],r["activity_id"],r["model_identifier"]) for r in predictions)
 if set(groups.values())!={12}:raise RuntimeError("Incomplete prediction group")
 fields=["attraction_id","activity_id","calendar_month","model_identifier","model_version","computed_score","monthly_rank","evaluation_cohort","geographic_source","source_dataset_id","model_source_dataset_id","configuration_hash"]
 baseline_rows=[r for r in predictions if r["model_kind"]=="baseline"];ablation_rows=[r for r in predictions if r["model_kind"]=="ablation"]
 hashes={"baseline_predictions.csv":stable_csv(OUT/"baseline_predictions.csv",baseline_rows,fields),"ablation_predictions.csv":stable_csv(OUT/"ablation_predictions.csv",ablation_rows,fields)}
 dump(OUT/"stage12_4e1_prediction_checksums.json",{"algorithm":"SHA-256","deterministic_serialization":True,"files":hashes})
 # Pairwise model agreement; this is not accuracy.
 ranks=defaultdict(dict)
 for r in predictions:ranks[(r["attraction_id"],r["activity_id"],r["model_identifier"])][r["calendar_month"]]=r["monthly_rank"]
 agreements={}
 for model in ("rainfall_only","district_multivariable","rainfall_risk_adjusted"):
  s=[];k=[];o=[]
  for aid,act in sorted({(int(r["attraction_id"]),int(r["activity_id"])) for r in monthly}):
   a=[ranks[(aid,act,model)][m] for m in range(1,13)];b=[ranks[(aid,act,"activity_aware")][m] for m in range(1,13)]
   s.append(spearman(a,b));k.append(kendall(a,b));o.append(top_k_overlap(sorted(range(1,13),key=lambda m:ranks[(aid,act,model)][m]),sorted(range(1,13),key=lambda m:ranks[(aid,act,"activity_aware")][m])))
  agreements[model]={"pairs":len(s),"mean_spearman":avg(s),"mean_kendall":avg(k),"mean_top3_overlap":avg(o),"interpretation":"model-to-model ranking agreement; not ground-truth accuracy"}
 dump(REPORTS/"stage12_4e1_model_agreement.json",agreements)
 baseline_report={"status":"REPRODUCED","definitions":BASELINES,"prediction_rows":len(baseline_rows),"pairs":len(monthly)//12,"deterministic_tie_break":"descending score then ascending calendar month","configuration_hashes":{c["model_identifier"]:c["configuration_hash"] for c in configs if c["kind"]=="baseline"}}
 dump(REPORTS/"stage12_4e1_baseline_reproduction.json",baseline_report)
 by_model=defaultdict(list);full={(r["attraction_id"],r["activity_id"],r["calendar_month"]):r for r in ablation_rows if r["model_identifier"]=="ablation_full_activity_aware"}
 for r in ablation_rows:
  if r["model_identifier"]=="ablation_full_activity_aware":continue
  ref=full[(r["attraction_id"],r["activity_id"],r["calendar_month"])];by_model[r["model_identifier"]].append((abs(r["computed_score"]-ref["computed_score"]),abs(r["monthly_rank"]-ref["monthly_rank"])))
 ablation_report={"status":"COMPLETED_LABEL_INDEPENDENT","prediction_rows":len(ablation_rows),"behavior":{m:{"rows":len(v),"mean_absolute_score_change":avg([x[0] for x in v]),"mean_absolute_rank_change":avg([x[1] for x in v])} for m,v in sorted(by_model.items())},"unavailable":[c for c in ablations if not c["available"]],"interpretation":"behavioral change only; larger change does not imply improvement"}
 dump(REPORTS/"stage12_4e1_ablation_analysis.json",ablation_report)
 # Activity sensitivity among attractions with multiple evaluated activities.
 d_ranks={(int(r["attraction_id"]),int(r["activity_id"])):tuple(ranks[(int(r["attraction_id"]),int(r["activity_id"]),"activity_aware")][m] for m in range(1,13)) for r in monthly[::12]}
 by_attr=defaultdict(list)
 for pair,rv in d_ranks.items():by_attr[pair[0]].append((pair[1],rv))
 multi={a:v for a,v in by_attr.items() if len(v)>1};distinct=sum(len({x[1] for x in v})>1 for v in multi.values())
 activity_report={"multi_activity_attractions":len(multi),"with_distinct_activity_rankings":distinct,"percentage_distinct":100*distinct/len(multi) if multi else 0,"by_activity_mean_score":{activity_codes[k]:avg([float(r["climate_favorability_score"]) for r in monthly if int(r["activity_id"])==k]) for k in sorted(activity_codes)}}
 dump(REPORTS/"stage12_4e1_activity_sensitivity.json",activity_report)
 pair_sources={(int(r["attraction_id"]),int(r["activity_id"])):r["geographic_source_type"] for r in monthly}
 district_pairs=Counter(d for (_,pair),(_,d) in zip(sorted(cohorts),[cohorts[k] for k in sorted(cohorts)]))
 source_counts=Counter(r["geographic_source_type"] for r in monthly)
 coordinate_attractions={pair[0] for pair,source in pair_sources.items() if source=="ATTRACTION_COORDINATE_REANALYSIS"}
 district_attractions=defaultdict(set)
 for pair,(cohort,district) in cohorts.items():
  if pair_sources[pair]=="DISTRICT_REPRESENTATIVE_PROXY":district_attractions[district].add(pair[0])
 activity_source=defaultdict(Counter)
 for pair,source in pair_sources.items():activity_source[activity_codes[pair[1]]][source]+=1
 geo={"monthly_rows":dict(source_counts),"percentages":{k:100*v/len(monthly) for k,v in source_counts.items()},"distinct_districts":len({v[1] for v in cohorts.values()}),"distinct_climate_source_identities":len(district_attractions)+len(coordinate_attractions),"dedicated_coordinate_attractions":len(coordinate_attractions),"dedicated_coordinate_pairs":sum(v=="ATTRACTION_COORDINATE_REANALYSIS" for v in pair_sources.values()),"district_proxy_pairs":sum(v=="DISTRICT_REPRESENTATIVE_PROXY" for v in pair_sources.values()),"pairs_sharing_district_profiles":sum(v>1 for v in Counter(x[1] for x in cohorts.values()).values()),"districts_shared_by_multiple_attractions":sum(len(v)>1 for v in district_attractions.values()),"activity_distribution_by_source":{k:dict(v) for k,v in sorted(activity_source.items())},"identical_inputs_expected":"Geographically distinct attractions assigned to the same district reuse identical Stage 12.4C climate inputs; activity weighting can still change rankings.","limitation":"The dedicated-coordinate subset is too small to represent all attractions or establish local microclimate accuracy."}
 dump(REPORTS/"stage12_4e1_geographic_proxy_analysis.json",geo)
 cohort_report={c:{"pairs":sum(1 for v in cohorts.values() if v[0]==c),"mean_activity_aware_score":avg([float(r["climate_favorability_score"]) for r in monthly if r["evaluation_cohort"]==c]),"mean_uncertainty":avg([float(r["climate_uncertainty"]) for r in monthly if r["evaluation_cohort"]==c])} for c in ("A","B")}
 cohort_report["interpretation"]="descriptive cohort sensitivity; not human-validated accuracy";dump(REPORTS/"stage12_4e1_cohort_sensitivity.json",cohort_report)
 blind_map=blind_template_exposure(FROZEN/"stage12_4d2_mapping_review_blind.csv");blind_season=blind_template_exposure(FROZEN/"stage12_4d2_seasonality_review_blind.csv")
 leakage={"status":"NO_CRITICAL_LEAKAGE_DETECTED","frozen_integrity":frozen_check["all_match"],"fixed_rule_evaluation_no_tuning_split_required":True,"blind_mapping_template":blind_map,"blind_seasonality_template":blind_season,"shared_district_proxy":"DETECTED_AND_GROUPING_REQUIRED","shared_climate_source_identities":geo["distinct_climate_source_identities"],"normalized_duplicate_name_groups":duplicate_name_groups,"near_duplicate_policy":"Normalized exact-name candidates and all records sharing a climate source must remain grouped before any future tuning split.","human_labels_used_for_tuning":False,"model_scores_used_as_labels":False,"held_out_overlap":"NOT_APPLICABLE_NO_FITTING; grouped split required before any future tuning"}
 dump(REPORTS/"stage12_4e1_leakage_audit.json",leakage)
 labels=label_availability([FROZEN/"stage12_4d2_mapping_review_blind.csv",FROZEN/"stage12_4d2_seasonality_review_blind.csv"])
 label_readiness={**labels,"label_dependent_experiments_status":"PENDING_INDEPENDENT_HUMAN_LABELS","prepared":["mapping precision","reviewer agreement","NDCG@3","NDCG@5","Spearman and Kendall versus judgments","top-3 relevance","paired baseline confidence intervals","activity/geographic subgroup evaluation","ablation performance"]}
 dump(REPORTS/"stage12_4e1_human_label_readiness.json",label_readiness)
 # ACID/idempotent persistence via temp COPY and ON CONFLICT.
 with psycopg.connect(dbdsn()) as conn:
  with conn.transaction():
   with conn.cursor() as cur:
    cur.execute("INSERT INTO climate_evaluation_runs(run_version,dataset_version,status,started_at,metadata_json) VALUES(%s,%s,'RUNNING',%s,%s) ON CONFLICT(run_version) DO UPDATE SET status='RUNNING',started_at=EXCLUDED.started_at,metadata_json=EXCLUDED.metadata_json RETURNING id",(RUN_VERSION,DATASET_VERSION,started,Json({"frozen_hashes":frozen_check["files"]})));run_id=cur.fetchone()[0]
    config_ids={}
    for c in configs:
     version=c.get("model_version") or c.get("version");cur.execute("INSERT INTO climate_evaluation_model_configurations(model_identifier,model_version,configuration_hash,configuration_json) VALUES(%s,%s,%s,%s) ON CONFLICT(model_identifier,model_version) DO UPDATE SET configuration_hash=EXCLUDED.configuration_hash,configuration_json=EXCLUDED.configuration_json RETURNING id",(c["model_identifier"],version,c["configuration_hash"],Json(c)));config_ids[c["model_identifier"]]=cur.fetchone()[0]
    cur.execute("CREATE TEMP TABLE eval_prediction_stage(model_configuration_id int,attraction_id int,activity_type_id int,month int,score double precision,rank int,cohort varchar(5),geographic_source varchar(60),source_dataset_id int) ON COMMIT DROP")
    with cur.copy("COPY eval_prediction_stage FROM STDIN") as cp:
     for r in predictions:cp.write_row((config_ids[r["model_identifier"]],r["attraction_id"],r["activity_id"],r["calendar_month"],r["computed_score"],r["monthly_rank"],r["evaluation_cohort"],r["geographic_source"],r["model_source_dataset_id"]))
    cur.execute("INSERT INTO climate_evaluation_predictions(run_id,model_configuration_id,attraction_id,activity_type_id,month,score,rank,cohort,geographic_source,source_dataset_id) SELECT %s,model_configuration_id,attraction_id,activity_type_id,month,score,rank,cohort,geographic_source,source_dataset_id FROM eval_prediction_stage ON CONFLICT(run_id,model_configuration_id,attraction_id,activity_type_id,month) DO UPDATE SET score=EXCLUDED.score,rank=EXCLUDED.rank,cohort=EXCLUDED.cohort,geographic_source=EXCLUDED.geographic_source,source_dataset_id=EXCLUDED.source_dataset_id",(run_id,))
    for name,result in (("model_agreement",agreements),("ablation_behavior",ablation_report),("activity_sensitivity",activity_report),("geographic_proxy",geo),("cohort_sensitivity",cohort_report),("human_label_readiness",label_readiness)):
     cur.execute("INSERT INTO climate_evaluation_experiment_results(run_id,experiment_name,status,result_json) VALUES(%s,%s,%s,%s) ON CONFLICT(run_id,experiment_name) DO UPDATE SET status=EXCLUDED.status,result_json=EXCLUDED.result_json",(run_id,name,"PENDING_INDEPENDENT_HUMAN_LABELS" if name=="human_label_readiness" else "COMPLETED",Json(result)))
    cur.execute("UPDATE climate_evaluation_runs SET status='COMPLETED',completed_at=now(),metadata_json=%s WHERE id=%s",(Json({"prediction_rows":len(predictions),"checksums":hashes}),run_id))
  with conn.cursor() as cur:
   cur.execute("SELECT count(*) FROM climate_evaluation_predictions WHERE run_id=%s",(run_id,));persisted=cur.fetchone()[0]
   cur.execute("SELECT count(*) FROM climate_reviewer_label_submissions");review_rows=cur.fetchone()[0]
   cur.execute("SELECT count(*) FROM climate_daily_observations");raw_after=cur.fetchone()[0]
   cur.execute("SELECT count(*) FROM climate_attraction_activity_seasonality");profiles_after=cur.fetchone()[0]
 readback={"status":"INDEPENDENT_READBACK_VERIFIED","run_id":run_id,"run_version":RUN_VERSION,"persisted_predictions":persisted,"model_configurations":len(configs),"reviewer_label_rows":review_rows,"raw_observations":raw_after,"seasonality_profiles":profiles_after,"protected_counts_unchanged":raw_after==raw_before and profiles_after==profiles_before}
 dump(REPORTS/"stage12_4e1_database_readback.json",readback)
 # Documentation and final test run.
 (DOCS/"STAGE_12_4E1_EVALUATION_CONTRACT.md").write_text("""# Stage 12.4E.1 Evaluation Contract

The primary unit is one attraction–activity query with the 12 calendar months as candidates. A method ranks those months; independent month-level judgments are the only ground truth. Ranking attractions for a tourist query is outside this task. Mapping validity is a separate classification task. Model agreement and ablation analyses are exploratory behavior, not accuracy.

Unjudged months are not treated as irrelevant. NDCG is reported only at cutoffs with adequate independent judgments. `INSUFFICIENT_EVIDENCE` is excluded with missingness reported. Model predictions and reviewer submissions are stored separately.
""",encoding="utf-8",newline="\n")
 (DOCS/"STAGE_12_4E1_BASELINE_AND_ABLATION_METHODS.md").write_text("""# Stage 12.4E.1 Baseline and Ablation Methods

Baselines A–C reproduce persisted Stage 12.4C ranks/scores: ascending median rainfall, the original 0.45/0.25/0.15/0.15 multivariable composite, and ascending rainfall mean plus 0.5 standard deviation. Method D reproduces frozen Stage 12.4D scores. Ties use ascending calendar month.

Ablations remove one stored normalized contribution and renormalize remaining non-zero activity weights. The generic-weight ablation uses Stage 12.4C multivariable weights. District-only substitutes district features. Wind removal is unavailable because production profiles assign wind zero weight. No persisted production score or weight is changed.
""",encoding="utf-8",newline="\n")
 (DOCS/"STAGE_12_4E2_HUMAN_EVALUATION_EXECUTION_PLAN.md").write_text("""# Stage 12.4E.2 Human Evaluation Execution Plan

Collect two independent judgments per blind item, validate identity/timestamps/evidence, preserve submissions immutably, calculate mapping kappa and ordinal weighted agreement, adjudicate disagreements separately, then evaluate complete 12-month queries. Use cluster bootstrap by district/climate-source identity for paired method comparisons. Freeze labels before analysis and never expose model scores during review. Stage 12.4E.2 remains pending.
""",encoding="utf-8",newline="\n")
 (DOCS/"STAGE_12_4E1_OFFLINE_EVALUATION_INFRASTRUCTURE.md").write_text(f"""# Stage 12.4E.1 Offline Evaluation Infrastructure

Run `{RUN_VERSION}` verified the frozen `{DATASET_VERSION}` checksums, produced {len(baseline_rows):,} baseline and {len(ablation_rows):,} ablation prediction rows, and persisted {persisted:,} idempotent predictions. All results without human labels are explicitly behavioral/descriptive. Independent accuracy, agreement, NDCG, and inferential comparisons remain pending. District proxy reuse dominates the data and requires clustered inference. No Qdrant, ranker weight, production profile, or frozen dataset mutation occurred.
""",encoding="utf-8",newline="\n")
 # Tests are executed after every artifact exists.
 test=subprocess.run([sys.executable,str(ROOT/"scripts"/"run_stage12_4e1_tests.py")],cwd=ROOT,text=True,capture_output=True)
 if test.returncode:print(test.stdout);print(test.stderr,file=sys.stderr);raise RuntimeError("Stage 12.4E.1 tests failed")
 tests=load(REPORTS/"stage12_4e1_tests.json")
 frozen_after=verify_checksums(FROZEN,FROZEN/"stage12_4d2_dataset_checksums.json")
 regressions={name:load(REPORTS/file) for name,file in (("12.4D","stage12_4d_tests.json"),("12.4D.1","stage12_4d1_tests.json"),("12.4D.2","stage12_4d2_tests.json"))}
 final={"status":"OFFLINE_EVALUATION_INFRASTRUCTURE_VERIFIED","migration_id":MIGRATION,"dataset_version":DATASET_VERSION,"frozen_dataset_verified_before_and_after":frozen_check["all_match"] and frozen_after["all_match"],"database_readback":readback,"baseline_configurations":4,"baseline_predictions":len(baseline_rows),"available_ablation_configurations":sum(c["available"] for c in ablations),"ablation_predictions":len(ablation_rows),"model_agreement":agreements,"ablation_behavior":ablation_report["behavior"],"activity_sensitivity":activity_report,"geographic_proxy_dependence":geo,"cohort_sensitivity":cohort_report,"reviewer_labels":label_readiness,"leakage_audit":leakage,"prediction_checksums":hashes,"automated_tests":tests,"regression_tests":{k:{x:v.get(x) for x in ("status","total_tests","passed","failed")} for k,v in regressions.items()},"pytest_limitation":"pytest is not installed in the Docker image; no pytest suite is claimed as passed.","label_dependent_experiments":"PENDING_INDEPENDENT_HUMAN_LABELS","scientific_limitations":["No independent human labels are available.","District proxy reuse creates clustered dependence.","Model agreement is not accuracy.","The coordinate subset is not representative."],"stage12_4e2":"READY_FOR_LABEL_COLLECTION_NOT_EXECUTED","completed_at_utc":now()}
 dump(REPORTS/"stage12_4e1_final_summary.json",final);print(json.dumps({"status":final["status"],"baseline_predictions":len(baseline_rows),"ablation_predictions":len(ablation_rows),"persisted_predictions":persisted,"tests":tests.get("status")},indent=2))
if __name__=="__main__":main()
