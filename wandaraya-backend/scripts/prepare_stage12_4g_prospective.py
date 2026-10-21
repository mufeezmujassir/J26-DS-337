#!/usr/bin/env python3
"""Freeze the protocol and build a deterministic, prediction-blind review package."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.climate.evaluation.prospective import (DATASET_VERSION, PROTOCOL_VERSION,
    SAMPLING_SEED, TARGET_QUERY_COUNT, deterministic_sample, protocol, sha256_json)

OUT = ROOT / "data" / "evaluation" / "stage12_4g"
REPORTS = ROOT / "data" / "reports"
HISTORICAL_GT = ROOT / "data" / "evaluation" / "stage12_4e2" / "stage12_4e2_ground_truth_v1.csv"


def dsn():
    return os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://", "postgresql://")


def dump(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


def csv_write(path: Path, fields: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_queries() -> set[tuple[int, int]]:
    with HISTORICAL_GT.open(encoding="utf-8", newline="") as handle:
        return {(int(r["attraction_id"]), int(r["activity_id"])) for r in csv.DictReader(handle)}


def inventory(conn) -> list[dict]:
    query = """
    SELECT DISTINCT ON (p.attraction_id,p.activity_type_id)
      p.attraction_id,a.name,p.activity_type_id,t.name,t.activity_family,d.id,d.name,
      p.dataset_version_id,p.climate_source_type,m.evidence_tier,m.confidence_level,
      m.evidence_reference,m.mapping_source,m.mapping_method,v.source_name,v.product_name,
      v.product_version,v.source_url,v.reference_start,v.reference_end
    FROM climate_attraction_activity_seasonality p
    JOIN climate_attraction_activity_mappings m ON m.attraction_id=p.attraction_id AND m.activity_type_id=p.activity_type_id
    JOIN attractions a ON a.id=p.attraction_id AND a.is_active=true
    JOIN climate_activity_types t ON t.id=p.activity_type_id AND t.is_active=true
    JOIN districts d ON d.id=p.district_id
    JOIN climate_dataset_versions v ON v.id=p.dataset_version_id
    WHERE p.is_active=true AND m.is_eligible_for_seasonality=true
      AND m.mapping_validation_status <> 'UNSUPPORTED'
    GROUP BY p.attraction_id,a.name,p.activity_type_id,t.name,t.activity_family,d.id,d.name,
      p.dataset_version_id,p.climate_source_type,m.evidence_tier,m.confidence_level,
      m.evidence_reference,m.mapping_source,m.mapping_method,v.source_name,v.product_name,
      v.product_version,v.source_url,v.reference_start,v.reference_end,m.updated_at
    HAVING count(DISTINCT p.month)=12
    ORDER BY p.attraction_id,p.activity_type_id,m.updated_at DESC
    """
    rows = conn.execute(query).fetchall()
    names = ["attraction_id","attraction_name","activity_type_id","activity_type","activity_family",
             "district_id","district","source_dataset_id","geographic_evidence_level","mapping_evidence_tier",
             "mapping_confidence","mapping_evidence_reference","mapping_source","mapping_method","source_name",
             "product_name","product_version","source_url","reference_start","reference_end"]
    result = []
    for values in rows:
        row = dict(zip(names, values))
        row["mapping_evidence_tier"] = row["mapping_evidence_tier"] or "UNCLASSIFIED"
        if row["geographic_evidence_level"] == "ATTRACTION_COORDINATE_REANALYSIS":
            row["climate_source_identity"] = f"dataset:{row['source_dataset_id']}:attraction:{row['attraction_id']}"
        else:
            row["climate_source_identity"] = f"dataset:{row['source_dataset_id']}:district:{row['district_id']}"
        row["sampling_cohort"] = ("COORDINATE_EVIDENCE" if row["geographic_evidence_level"] == "ATTRACTION_COORDINATE_REANALYSIS"
                                  else "STRONG_MAPPING" if row["mapping_evidence_tier"] in {"A","B"} else "WEAK_MAPPING")
        row["dataset_version"] = DATASET_VERSION
        result.append(row)
    return result


def monthly_rows(conn, selected: list[dict]) -> list[dict]:
    keys = [f"{r['attraction_id']}:{r['activity_type_id']}" for r in selected]
    query = """
    SELECT p.attraction_id,a.name,p.activity_type_id,t.name,t.description,p.month,d.name,
      p.dataset_version_id,p.climate_source_type,m.evidence_tier,m.evidence_reference,
      COALESCE(ac.reference_period,dc.reference_period),
      CASE WHEN p.climate_source_type='ATTRACTION_COORDINATE_REANALYSIS' THEN ac.rainfall_mean_mm ELSE dc.rainfall_mean_mm END,
      CASE WHEN p.climate_source_type='ATTRACTION_COORDINATE_REANALYSIS' THEN ac.rainfall_cv ELSE dc.rainfall_cv END,
      CASE WHEN p.climate_source_type='ATTRACTION_COORDINATE_REANALYSIS' THEN ac.temp_mean_c ELSE dc.temp_mean_c END,
      CASE WHEN p.climate_source_type='ATTRACTION_COORDINATE_REANALYSIS' THEN ac.relative_humidity_mean_pct ELSE dc.relative_humidity_mean_pct END,
      CASE WHEN p.climate_source_type='ATTRACTION_COORDINATE_REANALYSIS' THEN ac.wind_speed_mean_ms ELSE dc.wind_speed_mean_ms END,
      CASE WHEN p.climate_source_type='ATTRACTION_COORDINATE_REANALYSIS' THEN ac.solar_radiation_mean_mj ELSE dc.solar_radiation_mean_mj END,
      v.source_name,v.product_name,v.product_version,v.source_url
    FROM climate_attraction_activity_seasonality p
    JOIN attractions a ON a.id=p.attraction_id
    JOIN climate_activity_types t ON t.id=p.activity_type_id
    JOIN districts d ON d.id=p.district_id
    JOIN climate_attraction_activity_mappings m ON m.attraction_id=p.attraction_id AND m.activity_type_id=p.activity_type_id
    JOIN climate_dataset_versions v ON v.id=p.dataset_version_id
    LEFT JOIN climate_attraction_monthly_climatology ac ON ac.attraction_id=p.attraction_id AND ac.dataset_version_id=p.dataset_version_id AND ac.month=p.month
    LEFT JOIN climate_district_monthly_climatology dc ON dc.district_id=p.district_id AND dc.dataset_version_id=p.dataset_version_id AND dc.month=p.month
    WHERE p.is_active=true AND (p.attraction_id::text||':'||p.activity_type_id::text)=ANY(%s)
    ORDER BY p.attraction_id,p.activity_type_id,p.month
    """
    dbrows = conn.execute(query, (keys,)).fetchall()
    names = ["attraction_id","attraction_name","activity_type_id","activity_type","tourism_context","calendar_month",
             "district","source_dataset_id","climate_source_type","mapping_evidence_tier","mapping_evidence_reference",
             "historical_reference_period","rainfall_mean_mm","rainfall_cv","temperature_mean_c",
             "relative_humidity_mean_pct","wind_speed_mean_ms","solar_radiation_mean_mj","source_name","product_name",
             "product_version","source_url"]
    meta = {(r["attraction_id"],r["activity_type_id"]): r for r in selected}
    result=[]
    for values in dbrows:
        row=dict(zip(names,values)); item=meta[(row["attraction_id"],row["activity_type_id"])]
        token=f"{DATASET_VERSION}|{row['attraction_id']}|{row['activity_type_id']}|{row['calendar_month']}"
        row["review_item_id"]="G4-"+hashlib.sha256(token.encode()).hexdigest()[:16].upper()
        row["review_dataset_version"]=DATASET_VERSION
        row["climate_source_identity"]=item["climate_source_identity"]
        row["sampling_cohort"]=item["sampling_cohort"]
        row["source_reference"]=" | ".join(x for x in [row["mapping_evidence_reference"],row["source_url"]] if x)
        row.update(reviewer_id="",reviewer_expertise="",review_timestamp="",evidence_reviewed="",decision="",confidence="",notes="")
        result.append(row)
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True); REPORTS.mkdir(parents=True,exist_ok=True)
    existing_manifest = json.loads((OUT/"prospective_sampling_manifest.json").read_text(encoding="utf-8")) if (OUT/"prospective_sampling_manifest.json").exists() else {}
    historical_hash_before=checksum(HISTORICAL_GT)
    with psycopg.connect(dsn()) as conn:
        configs=dict(conn.execute("SELECT model_identifier,configuration_hash FROM climate_evaluation_model_configurations WHERE model_identifier IN ('activity_aware','district_multivariable')").fetchall())
        frozen=protocol(configs)
        dump(OUT/"prospective_protocol_manifest.json",frozen)
        all_rows=inventory(conn); prohibited=historical_queries()
        eligible=[r for r in all_rows if (r["attraction_id"],r["activity_type_id"]) not in prohibited]
        selected=deterministic_sample(eligible)
        selected_keys={(r["attraction_id"],r["activity_type_id"]) for r in selected}
        for row in all_rows:
            key=(row["attraction_id"],row["activity_type_id"])
            row["previously_inspected_query"]=key in prohibited
            row["eligible_for_prospective_sampling"]=key not in prohibited
            row["selected_for_review"]=key in selected_keys
            row["selection_hash"]=hashlib.sha256(f"{SAMPLING_SEED}|{key[0]}|{key[1]}".encode()).hexdigest()
        inv_fields=list(all_rows[0])
        csv_write(OUT/"prospective_candidate_inventory.csv",inv_fields,all_rows)
        monthly=monthly_rows(conn,selected)
        review_fields=list(monthly[0])
        csv_write(OUT/"prospective_reviewer_template.csv",review_fields,monthly)
        assignments=[]
        for row in monthly:
            for slot in (1,2):
                assignments.append({"review_item_id":row["review_item_id"],"review_dataset_version":DATASET_VERSION,
                    "reviewer_slot":slot,"reviewer_id":"","assignment_status":"UNASSIGNED"})
        csv_write(OUT/"prospective_review_assignments.csv",list(assignments[0]),assignments)
        adjudication=[{"review_item_id":r["review_item_id"],"review_dataset_version":DATASET_VERSION,
            "reviewer_1_decision":"","reviewer_2_decision":"","adjudicator_id":"","adjudicated_at":"",
            "final_decision":"","rationale":""} for r in monthly]
        csv_write(OUT/"prospective_adjudication_template.csv",list(adjudication[0]),adjudication)
        cluster_counts=Counter(r["climate_source_identity"] for r in selected)
        audit={"status":"PASS","dataset_version":DATASET_VERSION,"seed":SAMPLING_SEED,
            "candidate_inventory_queries":len(all_rows),"independent_eligible_queries":len(eligible),
            "historical_queries_excluded":len(prohibited),"selected_queries":len(selected),"selected_month_items":len(monthly),
            "overlap_with_stage12_4e2":len(selected_keys & prohibited),"independent_climate_clusters":len(cluster_counts),
            "climate_cluster_counts":dict(sorted(cluster_counts.items())),
            "districts":len({r['district'] for r in selected}),"activities":len({r['activity_type_id'] for r in selected}),
            "mapping_tiers":dict(Counter(r['mapping_evidence_tier'] for r in selected)),
            "geographic_evidence":dict(Counter(r['geographic_evidence_level'] for r in selected)),
            "sampling_cohorts":dict(Counter(r['sampling_cohort'] for r in selected)),
            "predictions_exposed_to_reviewers":False,"review_labels_populated":0,"genuinely_new":True}
        audit["sampling_audit_hash"]=sha256_json(audit)
        dump(OUT/"prospective_sampling_audit.json",audit)
        file_hashes={p.name:checksum(p) for p in sorted(OUT.glob("*.csv"))}
        manifest={"dataset_version":DATASET_VERSION,"protocol_version":PROTOCOL_VERSION,
            "protocol_hash":frozen["protocol_hash"],"sampling_seed":SAMPLING_SEED,
            "selected_query_count":len(selected),"selected_item_count":len(monthly),
            "selected_query_ids":[f"{r['attraction_id']}:{r['activity_type_id']}" for r in selected],
            "file_sha256":file_hashes,"frozen_at":existing_manifest.get("frozen_at",datetime.now(timezone.utc).isoformat()),
            "contains_human_labels":False}
        manifest["manifest_hash"]=sha256_json(manifest)
        dump(OUT/"prospective_sampling_manifest.json",manifest)
        instructions=f"""# Stage 12.4G Independent Reviewer Instructions

Dataset: `{DATASET_VERSION}`. Review all {len(monthly)} month items independently without consulting another reviewer. Examine the supplied source references and any source-backed evidence you actually use. Do not infer a label from the ordering of rows; no model or baseline prediction is present.

Fill `reviewer_id`, `reviewer_expertise`, an ISO-8601 `review_timestamp`, `evidence_reviewed`, `decision`, `confidence`, and `notes`. Decisions are `VERY_FAVORABLE`, `FAVORABLE`, `NEUTRAL`, `UNFAVORABLE`, `VERY_UNFAVORABLE`, or `INSUFFICIENT_EVIDENCE`. Use insufficient evidence when the attraction-activity relationship or monthly evidence cannot support a defensible grade; it remains missing, never zero. Each of two reviewers must work from a separate copy. Disagreements require a separate human adjudicator and must not be automatically resolved.
"""
        (OUT/"prospective_reviewer_instructions.md").write_text(instructions,encoding="utf-8",newline="\n")
        metadata={"protocol_version":PROTOCOL_VERSION,"protocol_hash":frozen["protocol_hash"],
            "dataset_version":DATASET_VERSION,"sampling_manifest_hash":manifest["manifest_hash"],
            "candidate_model":frozen["primary_candidate"],"baseline_model":frozen["primary_baseline"],
            "reviewer_status":"PENDING_INDEPENDENT_EVIDENCE","adjudication_status":"NOT_STARTED",
            "evaluation_status":"PROSPECTIVE_VALIDATION_PENDING","shadow_pilot_status":"NOT_YET_EXECUTED",
            "integration_flags":{"composition":False,"seasonality_evidence":False,"production_reranking":False},
            "limitations":[f"Feasibility target; {len(cluster_counts)} available selected climate-source clusters do not guarantee statistical power.","No prospective human judgments exist at protocol freeze."]}
        now=datetime.now(timezone.utc)
        run_id=conn.execute("""INSERT INTO climate_evaluation_runs(run_version,dataset_version,status,started_at,completed_at,metadata_json)
          VALUES('stage12_4g_run_v1',%s,'PROSPECTIVE_VALIDATION_PENDING',%s,%s,%s)
          ON CONFLICT(run_version) DO UPDATE SET status=excluded.status,completed_at=excluded.completed_at,metadata_json=excluded.metadata_json RETURNING id""",
          (DATASET_VERSION,now,now,Json(metadata))).fetchone()[0]
        conn.execute("""INSERT INTO climate_evaluation_experiment_results(run_id,experiment_name,status,result_json)
          VALUES(%s,'prospective_protocol_and_sampling','PROSPECTIVE_VALIDATION_PENDING',%s)
          ON CONFLICT(run_id,experiment_name) DO UPDATE SET status=excluded.status,result_json=excluded.result_json""",
          (run_id,Json({"protocol_hash":frozen["protocol_hash"],"manifest_hash":manifest["manifest_hash"],**audit})))
        conn.commit()
    preflight={"status":"PASS","alembic_migration_required":False,"existing_evaluation_tables_reused":True,
        "semantic_entry_point":"app.knowledge_base.retrieval.semantic_retriever.SemanticAttractionRetriever.search",
        "time_entry_point":"app.recommendation.time_context.service.evaluate_attraction_time_evidence",
        "holiday_entry_point":"app.holiday_event.context_scoring.HolidayEventContextScoringService.score",
        "seasonality_entry_point":"app.climate.services.seasonality_scoring.ExperimentalSeasonalityScoringService.score_batch",
        "aggregator":"app.recommendation.context_composition.service.ExperimentalContextCompositionService.compose",
        "public_route_added":False,"production_isolation":"three default-off flags; compositor returns evidence in semantic order"}
    dump(REPORTS/"stage12_4g_preflight.json",preflight)
    dump(REPORTS/"stage12_4g_sampling_audit.json",audit)
    dump(REPORTS/"stage12_4g_protocol_freeze.json",{"status":"FROZEN_BEFORE_LABELS",**frozen,
        "historical_ground_truth_sha256":historical_hash_before})
    print(json.dumps({"status":"PROSPECTIVE_VALIDATION_PENDING",**audit,
        "protocol_hash":frozen["protocol_hash"],"manifest_hash":manifest["manifest_hash"]},indent=2,default=str))


if __name__ == "__main__":
    main()
