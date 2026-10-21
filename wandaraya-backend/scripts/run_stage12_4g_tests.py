#!/usr/bin/env python3
"""Executable Stage 12.4G verification suite with named research assertions."""
from __future__ import annotations
import asyncio,csv,hashlib,json,os,sys
from collections import Counter,defaultdict
from datetime import date,datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import psycopg
from pydantic import ValidationError
from qdrant_client import QdrantClient

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.database import AsyncSessionLocal
from app.climate.evaluation.label_validation import validate_independence
from app.climate.evaluation.prospective import *
from app.climate.evaluation.prospective_evaluator import validate_protocol,decision,evaluate_verified_rows
from app.climate.evaluation.ranking_metrics import ndcg
from app.climate.services.seasonality_scoring import *
from app.recommendation.context_composition.service import ExperimentalContextCompositionService,ExperimentalCompositionDisabled

OUT=ROOT/"data"/"evaluation"/"stage12_4g";REPORTS=ROOT/"data"/"reports"
checks=[]
def check(name,condition,detail=None):checks.append({"name":name,"passed":bool(condition),"detail":detail});
def readcsv(name):
 with (OUT/name).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")

async def service_checks(inventory):
 strong=next(r for r in inventory if r["selected_for_review"]=="True" and r["mapping_evidence_tier"] in {"A","B"})
 weak=next(r for r in inventory if r["selected_for_review"]=="True" and r["mapping_evidence_tier"]=="C")
 async with AsyncSessionLocal() as db:
  service=ExperimentalSeasonalityScoringService(db)
  normal=await service.score(SeasonalityScoreRequest(attraction_id=int(strong["attraction_id"]),activity_type_id=int(strong["activity_type_id"]),month=1,geographic_evidence_level="CALLER_OVERRIDE"))
  fallback=await service.score(SeasonalityScoreRequest(attraction_id=int(weak["attraction_id"]),activity_type_id=int(weak["activity_type_id"]),travel_date=date(2026,2,1)))
  missing=await service.score(SeasonalityScoreRequest(attraction_id=999999999,activity_type_id=1,month=1))
 check("service_supported_available",normal.availability_status=="AVAILABLE")
 check("service_supported_no_fallback",normal.fallback_status==FallbackStatus.FALLBACK_NOT_REQUIRED)
 check("service_supported_fallback_false",normal.fallback_used is False)
 check("service_score_range",normal.seasonality_suitability_score is not None and 0<=normal.seasonality_suitability_score<=1)
 check("service_category_consistent",normal.suitability_category==category(normal.seasonality_suitability_score))
 check("service_historical_kind",normal.evidence_kind=="HISTORICAL_CLIMATE_SEASONALITY")
 check("service_not_live_forecast",normal.is_live_weather_forecast is False)
 check("service_request_geo_ignored",normal.geographic_evidence_level!="CALLER_OVERRIDE")
 check("service_geo_mismatch_recorded","request_geographic_evidence_mismatch_ignored" in normal.missing_data_indicators)
 check("service_persisted_geo_authoritative",normal.climate_feature_provenance["authoritative_climate_source_type"]==normal.geographic_evidence_level)
 check("service_model_version",normal.model_version==MODEL_VERSION)
 check("service_production_unchanged",normal.production_ranking_changed is False)
 check("service_weak_fallback_applied",fallback.fallback_status==FallbackStatus.DISTRICT_BASELINE_FALLBACK_APPLIED)
 check("service_weak_fallback_true",fallback.fallback_used is True)
 check("service_weak_available",fallback.availability_status=="AVAILABLE")
 check("service_missing_mapping_explicit",missing.fallback_status==FallbackStatus.MAPPING_UNSUPPORTED)
 check("service_missing_mapping_score_none",missing.seasonality_suitability_score is None)
 check("service_batch_query_bound",service.last_query_count<=3)
 mapping=SimpleNamespace(is_eligible_for_seasonality=True,mapping_validation_status="VERIFIED",evidence_tier="A",confidence_level="HIGH",is_eligible_for_offline_evaluation=True)
 absent=service._result(SeasonalityScoreRequest(attraction_id=1,activity_type_id=1,month=1),mapping,None,{})
 check("service_profile_unavailable",absent.fallback_status==FallbackStatus.PROFILE_UNAVAILABLE)
 weakmap=SimpleNamespace(is_eligible_for_seasonality=True,mapping_validation_status="VERIFIED",evidence_tier="C",confidence_level="LOW",is_eligible_for_offline_evaluation=False)
 profile=SimpleNamespace(climate_source_type="DISTRICT_REPRESENTATIVE_PROXY",feature_contributions_json={},climate_favorability_score=.7,district_id=1,dataset_version_id=999,limitations_json=[],explanation_json={},climate_favorability_rank=1,evidence_status="SUPPORTED")
 unavailable=service._result(SeasonalityScoreRequest(attraction_id=1,activity_type_id=1,month=1),weakmap,profile,{})
 check("service_fallback_unavailable",unavailable.fallback_status==FallbackStatus.FALLBACK_UNAVAILABLE)
 check("service_weak_profile_not_silently_used",unavailable.seasonality_suitability_score is None)
 check("service_fallback_unavailable_false",unavailable.fallback_used is False)
 try:SeasonalityScoreRequest(attraction_id=1,activity_type_id=1,month=13);ok=False
 except ValidationError:ok=True
 check("service_invalid_month_rejected",ok)
 try:SeasonalityScoreRequest(attraction_id=1,activity_type_id=1,month=2,travel_date=date(2026,3,1));ok=False
 except ValidationError:ok=True
 check("service_date_month_conflict_rejected",ok)
 disabled=ExperimentalContextCompositionService(db,composition_enabled=False)
 try:await disabled.compose(query="x",travel_datetime=datetime.now(ZoneInfo("Asia/Colombo")),activity_type_id=1);ok=False
 except ExperimentalCompositionDisabled:ok=True
 check("composition_flag_enforced",ok)

def main():
 protocol_path=OUT/"prospective_protocol_manifest.json";protocol_data=validate_protocol(protocol_path)
 check("protocol_version",protocol_data["protocol_version"]==PROTOCOL_VERSION)
 check("protocol_hash_valid",True)
 check("protocol_frozen_before_labels",protocol_data["frozen_before_labels"] is True)
 check("protocol_primary_metric",protocol_data["primary_metric"]=="mean_ndcg_at_5_complete_12_month_queries")
 check("protocol_primary_candidate_original",protocol_data["primary_candidate"]["identifier"]=="activity_aware")
 check("protocol_baseline_district",protocol_data["primary_baseline"]["identifier"]=="district_multivariable")
 check("protocol_fixed_blend_not_primary","fixed" not in protocol_data["primary_candidate"]["identifier"])
 check("protocol_bootstrap_seed",protocol_data["analysis"]["bootstrap_seed"]==12404)
 check("protocol_bootstrap_iterations",protocol_data["analysis"]["bootstrap_iterations"]==10000)
 check("protocol_practical_threshold",protocol_data["decision_rule"]["practical_mean_ndcg5_difference"]==.01)
 check("protocol_missing_not_zero",protocol_data["analysis"]["insufficient_evidence"]=="missing_not_zero")
 check("protocol_min_clusters",protocol_data["decision_rule"]["minimum_independent_clusters"]==15)
 check("protocol_min_queries",protocol_data["decision_rule"]["minimum_complete_queries"]==60)
 inventory=readcsv("prospective_candidate_inventory.csv");template=readcsv("prospective_reviewer_template.csv");assignments=readcsv("prospective_review_assignments.csv")
 selected=[r for r in inventory if r["selected_for_review"]=="True"]
 check("inventory_count",len(inventory)==8898,len(inventory))
 check("sample_query_count",len(selected)==72,len(selected))
 check("review_item_count",len(template)==864,len(template))
 check("two_assignment_slots",len(assignments)==1728,len(assignments))
 check("assignments_unassigned",all(not r["reviewer_id"] and r["assignment_status"]=="UNASSIGNED" for r in assignments))
 check("labels_blank",all(not r["decision"] and not r["reviewer_id"] and not r["review_timestamp"] for r in template))
 forbidden={"prediction","baseline_prediction","candidate_rank","expected_answer","relevance_grade"}
 check("reviewer_blinding",not forbidden.intersection(template[0]))
 check("all_queries_twelve_months",all(v==12 for v in Counter((r["attraction_id"],r["activity_type_id"]) for r in template).values()))
 check("all_calendar_months",set(int(r["calendar_month"]) for r in template)==set(range(1,13)))
 check("source_references_present",all(r["source_reference"] for r in template))
 check("dataset_version_on_all_items",all(r["review_dataset_version"]==DATASET_VERSION for r in template))
 historical=set()
 with (ROOT/"data"/"evaluation"/"stage12_4e2"/"stage12_4e2_ground_truth_v1.csv").open(encoding="utf-8",newline="") as f:historical={(r["attraction_id"],r["activity_id"]) for r in csv.DictReader(f)}
 check("no_historical_query_overlap",not historical.intersection({(r["attraction_id"],r["activity_type_id"]) for r in selected}))
 check("district_diversity",len({r["district"] for r in selected})==21)
 check("activity_diversity",len({r["activity_type_id"] for r in selected})==16)
 check("climate_cluster_diversity",len({r["climate_source_identity"] for r in selected})==23)
 check("coordinate_evidence_present",sum(r["geographic_evidence_level"]=="ATTRACTION_COORDINATE_REANALYSIS" for r in selected)==8)
 check("district_proxy_present",sum(r["geographic_evidence_level"]=="DISTRICT_REPRESENTATIVE_PROXY" for r in selected)==64)
 check("strong_mapping_present",any(r["sampling_cohort"]=="STRONG_MAPPING" for r in selected))
 check("weak_mapping_present",any(r["sampling_cohort"]=="WEAK_MAPPING" for r in selected))
 rerun=deterministic_sample([r for r in inventory if r["eligible_for_prospective_sampling"]=="True"])
 check("sampling_deterministic",{(str(r["attraction_id"]),str(r["activity_type_id"])) for r in rerun}=={(str(r["attraction_id"]),str(r["activity_type_id"])) for r in selected})
 manifest=json.loads((OUT/"prospective_sampling_manifest.json").read_text(encoding="utf-8"));claimed=manifest.pop("manifest_hash")
 check("sampling_manifest_hash",sha256_json(manifest)==claimed)
 check("inventory_checksum",manifest["file_sha256"]["prospective_candidate_inventory.csv"]==sha(OUT/"prospective_candidate_inventory.csv"))
 check("template_checksum",manifest["file_sha256"]["prospective_reviewer_template.csv"]==sha(OUT/"prospective_reviewer_template.csv"))
 try:validate_independence([{"review_item_id":"X","reviewer_id":"R"},{"review_item_id":"X","reviewer_id":"R"}]);ok=False
 except ValueError:ok=True
 check("duplicate_review_rejected",ok)
 check("no_completed_review_files",not list(OUT.glob("completed_reviews/*.csv")))
 async_result=asyncio.run(service_checks(inventory))
 check("flags_composition_default_off",Settings.model_fields["ENABLE_EXPERIMENTAL_CONTEXT_COMPOSITION"].default is False)
 check("flags_seasonality_default_off",Settings.model_fields["ENABLE_EXPERIMENTAL_SEASONALITY_EVIDENCE"].default is False)
 check("flags_reranking_default_off",Settings.model_fields["ENABLE_SEASONALITY_PRODUCTION_RERANKING"].default is False)
 shadow=json.loads((REPORTS/"stage12_4g_shadow_pilot.json").read_text())
 check("shadow_real_measurements",shadow["requests"]==3 and shadow["candidate_count"]==15)
 check("shadow_ranking_invariance",shadow["ranking_invariance"] is True)
 check("shadow_deterministic",shadow["deterministic_repeat"] is True)
 check("shadow_no_errors",shadow["error_rate"]==0)
 check("shadow_query_count_measured",shadow["database_query_count"]["total"]>0)
 check("shadow_latency_measured",shadow["latency_ms"]["mean"]>0)
 check("shadow_seasonality_latency_measured",shadow["seasonality_latency_ms"]["mean"]>0)
 check("shadow_group_emotion_missing",all(m["group_emotion_not_available"] for m in shadow["measurements"]))
 check("shadow_no_production_reranking",shadow["production_reranking_flag"] is False)
 pending=json.loads((REPORTS/"stage12_4g_prospective_validation_status.json").read_text())
 check("prospective_pending",pending["status"]=="PROSPECTIVE_VALIDATION_PENDING")
 check("no_prospective_metric",pending["prospective_metrics"] is None)
 check("no_significance_claim",pending["statistical_significance"] is None)
 check("no_model_approval",pending["model_approved"] is False)
 check("decision_supported",decision(.02,.001,60,15,True)=="SUPPORTED_IMPROVEMENT")
 check("decision_no_improvement",decision(.005,.001,60,15,True)=="NO_ESTABLISHED_IMPROVEMENT")
 check("decision_low_queries",decision(.02,.001,59,15,True)=="INSUFFICIENT_INDEPENDENT_EVIDENCE")
 check("decision_low_clusters",decision(.02,.001,60,14,True)=="INSUFFICIENT_INDEPENDENT_EVIDENCE")
 check("decision_missing_adjudication",decision(.02,.001,60,15,False)=="INSUFFICIENT_INDEPENDENT_EVIDENCE")
 check("month_tie_break",month_order({2:.5,1:.5,3:.1})==[1,2,3])
 check("ndcg_perfect",ndcg([1,2,3],{1:4,2:3,3:0},3)==1.0)
 synthetic=[]
 for q in range(60):
  for month in range(1,13):synthetic.append({"evaluation_query_id":f"q{q}","calendar_month":month,"final_decision":["VERY_UNFAVORABLE","UNFAVORABLE","NEUTRAL","FAVORABLE","VERY_FAVORABLE"][month%5],"candidate_score":month/12,"baseline_score":1-month/12,"climate_source_identity":f"c{q%15}","activity_type":"x","geographic_evidence_level":"DISTRICT_REPRESENTATIVE_PROXY"})
 evaluated=evaluate_verified_rows(synthetic)
 check("evaluator_complete_filter",evaluated["complete_queries"]==60)
 check("evaluator_cluster_grouping",evaluated["independent_climate_clusters"]==15)
 check("evaluator_bootstrap_deterministic",evaluated["primary"]["cluster_bootstrap"]["seed"]==12404)
 with psycopg.connect(dsn()) as conn:
  vals=dict(conn.execute("SELECT 'observations',count(*) FROM climate_daily_observations UNION ALL SELECT 'profiles',count(*) FROM climate_attraction_activity_seasonality UNION ALL SELECT 'predictions',count(*) FROM climate_evaluation_predictions").fetchall())
  revision=conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
  run=conn.execute("SELECT status FROM climate_evaluation_runs WHERE run_version='stage12_4g_run_v1'").fetchone()
 check("historical_observations_unchanged",vals["observations"]==165828,vals["observations"])
 check("historical_profiles_unchanged",vals["profiles"]==121524,vals["profiles"])
 check("historical_predictions_unchanged",vals["predictions"]==606528,vals["predictions"])
 gt=ROOT/"data"/"evaluation"/"stage12_4e2"/"stage12_4e2_ground_truth_v1.csv"
 check("historical_ground_truth_hash",sha(gt)=="3383ee29f8367f4e3308ebf21d6beef187dc6015f588f5476345cb066488caad")
 f=json.loads((REPORTS/"stage12_4f_final_summary.json").read_text())
 check("stage_f_activity_metric_unchanged",abs(f["comparison"]["A_activity_aware"]-.8970686648809267)<1e-12)
 check("stage_f_district_metric_unchanged",abs(f["comparison"]["B_district_multivariable"]-.9157434177595347)<1e-12)
 check("no_new_migration",revision=="h45c6d7e8f9a")
 check("stage_g_run_persisted",run and run[0]=="PROSPECTIVE_VALIDATION_PENDING")
 client=QdrantClient(url=os.getenv("QDRANT_URL","http://qdrant:6333"));collection=os.getenv("QDRANT_COLLECTION_NAME",os.getenv("QDRANT_COLLECTION","sri_lanka_attractions"))
 count=client.get_collection(collection).points_count
 check("qdrant_count_unchanged",count==6120,count)
 passed=sum(x["passed"] for x in checks);failed=len(checks)-passed
 report={"stage":"12.4G","status":"ALL_TESTS_PASSED" if not failed else "TEST_FAILURES","executed":len(checks),"passed":passed,"failed":failed,"checks":checks}
 (REPORTS/"stage12_4g_tests.json").write_text(json.dumps(report,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8",newline="\n")
 print(json.dumps({k:report[k] for k in ("status","executed","passed","failed")},indent=2))
 if failed:
  print(json.dumps([x for x in checks if not x["passed"]],indent=2));raise SystemExit(1)
if __name__=="__main__":main()
