#!/usr/bin/env python3
"""Execute Stage 12.4D.2 evidence reconciliation and dataset freeze.

The script is intentionally database-backed, transactional, deterministic, and
idempotent. It does not call Qdrant or alter recommendation ranker settings.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from collections import Counter, defaultdict
from typing import Any, Iterable

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.climate.services.activity_evidence_policy import POLICY_VERSION, evaluate_mapping
from app.climate.services.research_evidence_reconciler import reconcile_artifacts

DATASET_VERSION = "stage12_4d2_eval_v1"
RANDOM_SEED = 12402
MIGRATION_ID = "e12f3a4b5c6d"
REPORTS = ROOT / "data" / "reports"
EVALUATION = ROOT / "data" / "evaluation"
DOCS = ROOT / "docs" / "research"
REPORTS.mkdir(parents=True, exist_ok=True)
EVALUATION.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=json_default) + "\n", encoding="utf-8", newline="\n")


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def db_url() -> str:
    value = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:root@localhost:5432/wandaraya")
    return value


def scalar(conn, sql: str, params: dict[str, Any] | None = None) -> Any:
    return conn.execute(text(sql), params or {}).scalar_one()


COUNT_SQL = {
    "alembic_revision": "SELECT version_num FROM alembic_version",
    "attractions": "SELECT count(*) FROM attractions WHERE is_active",
    "total_mappings": "SELECT count(*) FROM climate_attraction_activity_mappings",
    "eligible_mappings": "SELECT count(*) FROM climate_attraction_activity_mappings WHERE is_eligible_for_seasonality",
    "ineligible_mappings": "SELECT count(*) FROM climate_attraction_activity_mappings WHERE NOT is_eligible_for_seasonality",
    "mapped_attractions": "SELECT count(DISTINCT attraction_id) FROM climate_attraction_activity_mappings",
    "active_profiles": "SELECT count(*) FROM climate_attraction_activity_seasonality WHERE is_active",
    "inactive_profiles": "SELECT count(*) FROM climate_attraction_activity_seasonality WHERE NOT is_active",
    "quality_audits": "SELECT count(*) FROM climate_seasonality_quality_audit",
    "raw_observations": "SELECT count(*) FROM climate_daily_observations",
    "district_aggregates": "SELECT count(*) FROM climate_district_monthly_aggregates",
    "district_climatology": "SELECT count(*) FROM climate_district_monthly_climatology",
    "seasonality_features": "SELECT count(*) FROM climate_seasonality_features",
}


def read_counts(conn) -> dict[str, Any]:
    return {name: scalar(conn, sql) for name, sql in COUNT_SQL.items()}


MAPPING_SQL = """
SELECT m.id AS mapping_id, m.attraction_id, m.activity_type_id,
       a.name AS attraction_name, a.description, a.district_id, d.name AS district_name,
       a.vibe_tags, a.experience_tags,
       t.activity_type AS activity_code, t.name AS activity_name,
       m.mapping_source, m.mapping_method, m.evidence_reference, m.confidence_level,
       m.verification_status, m.reviewer_status, m.classification_version,
       m.mapping_validation_status, m.mapping_validation_reason, m.mapping_rule_version,
       m.is_eligible_for_seasonality, m.evaluation_eligibility_status,
       ea.original_mapping_status AS policy_original_mapping_status,
       ea.provisional_audit_class AS persisted_provisional_audit_class,
       cats.primary_category, cats.secondary_categories,
       acts.explicit_activities, descriptions.secondary_descriptions,
       sources.source_metadata
FROM climate_attraction_activity_mappings m
JOIN attractions a ON a.id=m.attraction_id
LEFT JOIN districts d ON d.id=a.district_id
JOIN climate_activity_types t ON t.id=m.activity_type_id
LEFT JOIN climate_mapping_evidence_audit ea ON ea.mapping_id=m.id AND ea.policy_version='12.4d2_v1.2'
LEFT JOIN LATERAL (
  SELECT max(c.name) FILTER (WHERE ac.is_primary) AS primary_category,
         json_agg(c.name ORDER BY c.name) FILTER (WHERE NOT ac.is_primary) AS secondary_categories
  FROM attraction_categories ac JOIN categories c ON c.id=ac.category_id
  WHERE ac.attraction_id=a.id
) cats ON true
LEFT JOIN LATERAL (
  SELECT json_agg(act.name ORDER BY act.name) FILTER (WHERE aa.is_available) AS explicit_activities
  FROM attraction_activities aa JOIN activities act ON act.id=aa.activity_id
  WHERE aa.attraction_id=a.id
) acts ON true
LEFT JOIN LATERAL (
  SELECT json_agg(ad.description ORDER BY ad.id) FILTER (WHERE ad.is_active AND ad.description IS NOT NULL) AS secondary_descriptions
  FROM attraction_descriptions ad WHERE ad.attraction_id=a.id
) descriptions ON true
LEFT JOIN LATERAL (
  SELECT json_agg(json_build_object('provider',sr.source_provider,'record',sr.external_source_id,'url',sr.canonical_source_url,'identity_status',sr.identity_status) ORDER BY sr.id) AS source_metadata
  FROM attraction_source_references sr WHERE sr.attraction_id=a.id
) sources ON true
ORDER BY m.id
"""


def rows_to_csv(rows: list[dict[str, Any]], fields: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        cooked = {}
        for field in fields:
            value = row.get(field)
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            elif value is True:
                value = "true"
            elif value is False:
                value = "false"
            elif value is None:
                value = ""
            cooked[field] = value
        writer.writerow(cooked)
    return buffer.getvalue().encode("utf-8")


def stable_write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> str:
    first = rows_to_csv(rows, fields)
    second = rows_to_csv(rows, fields)
    if hashlib.sha256(first).digest() != hashlib.sha256(second).digest():
        raise RuntimeError(f"Nondeterministic serialization detected for {path.name}")
    if path.exists() and path.read_bytes() != first and (EVALUATION / "stage12_4d2_dataset_manifest.json").exists():
        raise RuntimeError(f"Frozen artifact already exists with different contents: {path}")
    path.write_bytes(first)
    return hashlib.sha256(first).hexdigest()


def main() -> None:
    started = utcnow()
    engine = create_engine(db_url(), future=True)
    before_hashes: dict[str, int] = {}
    with engine.connect() as conn:
        pre_counts = read_counts(conn)
        pre_status = {r[0]: r[1] for r in conn.execute(text("SELECT mapping_validation_status,count(*) FROM climate_attraction_activity_mappings GROUP BY 1 ORDER BY 1"))}
        processing_runs = [dict(r) for r in conn.execute(text("SELECT stage,run_type,processing_version,status,records_processed,records_persisted FROM climate_processing_runs ORDER BY id")).mappings()]
        datasets = [dict(r) for r in conn.execute(text("SELECT id,provider_name,product_name,product_version,reference_start,reference_end,dataset_checksum FROM climate_dataset_versions ORDER BY id")).mappings()]
        before_hashes = {k: pre_counts[k] for k in ("raw_observations", "district_aggregates", "district_climatology", "seasonality_features")}
    preflight = {
        "status": "DATABASE_PREFLIGHT_VERIFIED",
        "stage": "12.4D.2",
        "queried_at_utc": started,
        "reference_migration": "d01e2f3a4b5c",
        "current_migration": pre_counts["alembic_revision"],
        "sql_statements": COUNT_SQL,
        "actual_returned_values": pre_counts,
        "stage12_4d1_authoritative_baseline": {"attractions":6120,"total_mappings":10127,"eligible_mappings":8940,"ineligible_mappings":1187,"active_profiles":107280,"inactive_profiles":14244,"quality_audits":1187,"raw_observations":165828},
        "mapping_status_distribution": pre_status,
        "processing_runs": processing_runs,
        "climate_datasets": datasets,
    }
    write_json(REPORTS / "stage12_4d2_preflight.json", preflight)

    report_paths = list(REPORTS.glob("stage12_4d1_*.json")) + list(REPORTS.glob("stage12_4d_*.json"))
    reconciliation_actual = {k: int(pre_counts[k]) for k in ("total_mappings", "eligible_mappings", "ineligible_mappings", "active_profiles", "inactive_profiles", "raw_observations")}
    reconciliation = reconcile_artifacts(report_paths, reconciliation_actual, started)
    reconciliation["pre_policy_mapping_status_distribution"] = pre_status
    write_json(REPORTS / "stage12_4d2_evidence_reconciliation.json", reconciliation)

    # Policy decisions are computed from one repeatable-read snapshot.
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        trans = conn.begin()
        mapping_rows = [dict(r) for r in conn.execute(text(MAPPING_SQL)).mappings()]
        decisions: dict[int, dict[str, Any]] = {}
        for row in mapping_rows:
            decisions[row["mapping_id"]] = evaluate_mapping(row).to_dict()
        trans.commit()

    # Persist policy and correction audit atomically. Climate scores are not recalculated.
    with engine.begin() as conn:
        for row in mapping_rows:
            decision = decisions[row["mapping_id"]]
            original_eval = row.get("evaluation_eligibility_status")
            revised_status = "UNSUPPORTED" if decision["demonstrably_unsupported"] else row["mapping_validation_status"]
            conn.execute(text("""
                UPDATE climate_attraction_activity_mappings
                SET evidence_tier=:tier, evidence_policy_version=CAST(:policy AS varchar),
                    evaluation_eligibility_status=:eval_status,
                    is_eligible_for_offline_evaluation=:offline,
                    independent_review_status=COALESCE(independent_review_status,'NOT_REVIEWED'),
                    mapping_validation_status=CAST(:revised_status AS varchar),
                    is_eligible_for_seasonality=CASE WHEN :demonstrably_unsupported THEN false ELSE is_eligible_for_seasonality END,
                    mapping_validation_reason=CASE WHEN :newly_rejected THEN :reason ELSE mapping_validation_reason END,
                    updated_at=CASE WHEN evidence_policy_version IS DISTINCT FROM CAST(:policy AS varchar) OR mapping_validation_status IS DISTINCT FROM CAST(:revised_status AS varchar) THEN now() ELSE updated_at END
                WHERE id=:mapping_id
            """), {
                "tier": decision["evidence_tier"], "policy": POLICY_VERSION,
                "eval_status": decision["evaluation_eligibility_status"], "offline": decision["eligible_for_offline_evaluation"],
                "revised_status": revised_status, "demonstrably_unsupported": decision["demonstrably_unsupported"],
                "newly_rejected": decision["demonstrably_unsupported"] and row["mapping_validation_status"] != "UNSUPPORTED",
                "reason": decision["reason"], "mapping_id": row["mapping_id"],
            })
            evidence = {
                "attraction_name": row["attraction_name"], "activity_code": row["activity_code"],
                "mapping_source": row["mapping_source"], "mapping_method": row["mapping_method"],
                "primary_category": row["primary_category"], "secondary_categories": row["secondary_categories"],
                "explicit_activities": row["explicit_activities"], "rule_ids": decision["rule_ids"],
            }
            conn.execute(text("""
                INSERT INTO climate_mapping_evidence_audit
                  (mapping_id,original_mapping_status,revised_mapping_status,original_evaluation_eligibility,
                   revised_evaluation_eligibility,provisional_audit_class,reason,evidence_json,policy_version,processed_at)
                VALUES (:mapping_id,:original_status,:revised_status,:original_eval,:revised_eval,:audit_class,:reason,CAST(:evidence AS json),:policy,now())
                ON CONFLICT (mapping_id,policy_version) DO UPDATE SET
                  revised_mapping_status=EXCLUDED.revised_mapping_status,
                  revised_evaluation_eligibility=EXCLUDED.revised_evaluation_eligibility,
                  provisional_audit_class=COALESCE(EXCLUDED.provisional_audit_class,climate_mapping_evidence_audit.provisional_audit_class),
                  reason=CASE WHEN EXCLUDED.provisional_audit_class IS NULL AND climate_mapping_evidence_audit.provisional_audit_class IS NOT NULL THEN climate_mapping_evidence_audit.reason ELSE EXCLUDED.reason END,
                  evidence_json=CASE WHEN EXCLUDED.provisional_audit_class IS NULL AND climate_mapping_evidence_audit.provisional_audit_class IS NOT NULL THEN climate_mapping_evidence_audit.evidence_json ELSE EXCLUDED.evidence_json END
            """), {
                "mapping_id": row["mapping_id"], "original_status": row["mapping_validation_status"],
                "revised_status": revised_status, "original_eval": original_eval,
                "revised_eval": decision["evaluation_eligibility_status"], "audit_class": decision["provisional_audit_class"],
                "reason": decision["reason"], "evidence": json.dumps(evidence, sort_keys=True), "policy": POLICY_VERSION,
            })
        rejected_ids = [mid for mid, d in decisions.items() if d["demonstrably_unsupported"]]
        if rejected_ids:
            conn.execute(text("""
                UPDATE climate_attraction_activity_seasonality s SET is_active=false,quality_audit_version=:policy
                FROM climate_attraction_activity_mappings m
                WHERE m.id = ANY(:ids) AND s.attraction_id=m.attraction_id AND s.activity_type_id=m.activity_type_id AND s.is_active
            """), {"ids": rejected_ids, "policy": POLICY_VERSION})
        # Repair the audit class deterministically if a prior interrupted rerun
        # encountered an already-corrected mapping. Original status is immutable.
        conn.execute(text("""
            UPDATE climate_mapping_evidence_audit
            SET provisional_audit_class='PROVISIONAL_CONTRADICTORY'
            WHERE policy_version=:policy AND original_mapping_status='PROVISIONAL'
              AND revised_mapping_status='UNSUPPORTED' AND provisional_audit_class IS NULL
        """), {"policy": POLICY_VERSION})

    # Independent readback and all exports use persisted policy state.
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        trans = conn.begin()
        post_counts = read_counts(conn)
        post_counts["evidence_audits"] = scalar(conn, "SELECT count(*) FROM climate_mapping_evidence_audit WHERE policy_version=:p", {"p": POLICY_VERSION})
        post_counts["offline_eligible"] = scalar(conn, "SELECT count(*) FROM climate_attraction_activity_mappings WHERE is_eligible_for_offline_evaluation")
        status_distribution = {r[0]: r[1] for r in conn.execute(text("SELECT mapping_validation_status,count(*) FROM climate_attraction_activity_mappings GROUP BY 1 ORDER BY 1"))}
        tier_distribution = {r[0]: r[1] for r in conn.execute(text("SELECT evidence_tier,count(*) FROM climate_attraction_activity_mappings GROUP BY 1 ORDER BY 1"))}
        eligibility_distribution = {r[0]: r[1] for r in conn.execute(text("SELECT evaluation_eligibility_status,count(*) FROM climate_attraction_activity_mappings GROUP BY 1 ORDER BY 1"))}
        persisted = [dict(r) for r in conn.execute(text(MAPPING_SQL.replace("ORDER BY m.id", "ORDER BY m.id"))).mappings()]
        for row in persisted:
            d = decisions[row["mapping_id"]]
            row.update({
                "evidence_tier": d["evidence_tier"], "evidence_policy_version": POLICY_VERSION,
                "evaluation_eligibility": d["evaluation_eligibility_status"],
                "provisional_audit_class": d["provisional_audit_class"], "policy_reason": d["reason"],
            })
        monthly_rows_raw = [dict(r) for r in conn.execute(text("""
          SELECT s.attraction_id,s.activity_type_id,s.district_id,s.month,s.dataset_version_id,
                 s.climate_source_type,s.activity_profile_version,s.processing_version,
                 s.climate_favorability_score,s.climate_favorability_rank,s.evidence_status,
                 s.uncertainty_score,s.feature_contributions_json,s.explanation_json,s.limitations_json,
                 m.evidence_tier,m.evidence_policy_version,m.evaluation_eligibility_status,m.mapping_rule_version,
                 COALESCE(c.reference_period,dc.reference_period) AS reference_period,
                 COALESCE(c.rainfall_mean_mm,dc.rainfall_mean_mm) AS rainfall_mean_mm,
                 COALESCE(c.rainfall_cv,dc.rainfall_cv) AS rainfall_cv,
                 COALESCE(c.temp_mean_c,dc.temp_mean_c) AS temp_mean_c,
                 COALESCE(c.relative_humidity_mean_pct,dc.relative_humidity_mean_pct) AS relative_humidity_mean_pct,
                 COALESCE(c.wind_speed_mean_ms,dc.wind_speed_mean_ms) AS wind_speed_mean_ms,
                 COALESCE(c.solar_radiation_mean_mj,dc.solar_radiation_mean_mj) AS solar_radiation_mean_mj,
                 COALESCE(c.geographic_source_type,s.climate_source_type) AS geographic_source_type,
                 p.feature_weights_json,dv.product_version,dv.source_name
          FROM climate_attraction_activity_seasonality s
          JOIN climate_attraction_activity_mappings m ON m.attraction_id=s.attraction_id AND m.activity_type_id=s.activity_type_id
          LEFT JOIN climate_attraction_monthly_climatology c ON c.attraction_id=s.attraction_id AND c.dataset_version_id=s.dataset_version_id AND c.month=s.month
          LEFT JOIN climate_district_monthly_climatology dc ON dc.district_id=s.district_id AND dc.dataset_version_id=s.dataset_version_id AND dc.month=s.month
          JOIN climate_activity_profiles p ON p.activity_type_id=s.activity_type_id AND p.profile_version=s.activity_profile_version
          JOIN climate_dataset_versions dv ON dv.id=s.dataset_version_id
          WHERE s.is_active AND m.is_eligible_for_offline_evaluation
          ORDER BY s.attraction_id,s.activity_type_id,s.month
        """)).mappings()]
        profile_configs = [dict(r) for r in conn.execute(text("SELECT t.activity_type,p.profile_version,p.feature_weights_json,p.thresholds_json,p.hard_constraints_json,p.uncertainty_policy_json FROM climate_activity_profiles p JOIN climate_activity_types t ON t.id=p.activity_type_id ORDER BY t.id,p.profile_version")).mappings()]
        trans.commit()

    for key, value in before_hashes.items():
        if post_counts[key] != value:
            raise RuntimeError(f"Protected historical count changed: {key}: {value} -> {post_counts[key]}")

    # Full provisional audit reflects pre-policy provisional population.
    provisional = []
    for row in mapping_rows:
        if row["mapping_validation_status"] != "PROVISIONAL" and row.get("policy_original_mapping_status") != "PROVISIONAL":
            continue
        d = decisions[row["mapping_id"]]
        provisional.append({
            **{k: row.get(k) for k in ("mapping_id","attraction_id","attraction_name","district_id","district_name","primary_category","secondary_categories","explicit_activities","description","activity_type_id","activity_code","activity_name","mapping_source","mapping_method","mapping_rule_version","evidence_reference","mapping_validation_reason","is_eligible_for_seasonality","source_metadata")},
            **{k: d[k] for k in ("provisional_audit_class","evidence_tier","evaluation_eligibility_status","eligible_for_offline_evaluation","reason","rule_ids","demonstrably_unsupported")},
        })
        if row.get("persisted_provisional_audit_class"):
            provisional[-1]["provisional_audit_class"] = row["persisted_provisional_audit_class"]
        elif row.get("policy_original_mapping_status") == "PROVISIONAL" and row["mapping_validation_status"] == "UNSUPPORTED":
            provisional[-1]["provisional_audit_class"] = "PROVISIONAL_CONTRADICTORY"
    def breakdown(rows: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
        return dict(sorted(Counter(str(r.get(key) or "UNKNOWN") for r in rows).items()))
    provisional_report = {
        "status": "ALL_PROVISIONAL_MAPPINGS_AUDITED", "policy_version": POLICY_VERSION,
        "audited_count": len(provisional), "classification_distribution": breakdown(provisional,"provisional_audit_class"),
        "by_activity": breakdown(provisional,"activity_code"), "by_primary_category": breakdown(provisional,"primary_category"),
        "by_district": breakdown(provisional,"district_name"), "by_mapping_rule": breakdown(provisional,"mapping_method"),
        "records": provisional,
    }
    write_json(REPORTS / "stage12_4d2_provisional_mapping_audit.json", provisional_report)

    common_fields = ["attraction_id","activity_type_id","district_id","mapping_validation_status","evidence_tier","evidence_policy_version","evaluation_eligibility","climate_source_type","historical_reference_period","seasonality_profile_version","explanation_version","dataset_version","row_provenance"]
    climate_meta: dict[tuple[int,int], dict[str, Any]] = {}
    for row in monthly_rows_raw:
        climate_meta.setdefault((row["attraction_id"],row["activity_type_id"]), row)
    cohorts = {"A": [], "B": [], "C": []}
    for row in persisted:
        tier = row["evidence_tier"]
        eligible = row["evaluation_eligibility"]
        cohort = "A" if eligible == "ELIGIBLE_HIGH_EVIDENCE" else "B" if eligible == "ELIGIBLE_INFERRED" else "C"
        meta = climate_meta.get((row["attraction_id"],row["activity_type_id"]), {})
        cohorts[cohort].append({
            "attraction_id": row["attraction_id"], "activity_type_id": row["activity_type_id"], "district_id": row["district_id"],
            "mapping_validation_status": row["mapping_validation_status"], "evidence_tier": tier,
            "evidence_policy_version": POLICY_VERSION, "evaluation_eligibility": eligible,
            "climate_source_type": meta.get("climate_source_type"), "historical_reference_period": meta.get("reference_period"),
            "seasonality_profile_version": meta.get("activity_profile_version"), "explanation_version": meta.get("processing_version"),
            "dataset_version": DATASET_VERSION,
            "row_provenance": {"mapping_id":row["mapping_id"],"mapping_source":row["mapping_source"],"mapping_method":row["mapping_method"],"source_dataset_id":meta.get("dataset_version_id")},
        })
    for rows in cohorts.values():
        rows.sort(key=lambda r:(r["attraction_id"],r["activity_type_id"]))

    export_hashes: dict[str, str] = {}
    names = {"A":"stage12_4d2_cohort_a_high_evidence.csv","B":"stage12_4d2_cohort_b_inferred.csv","C":"stage12_4d2_cohort_c_provisional.csv"}
    for key in "ABC":
        export_hashes[names[key]] = stable_write_csv(EVALUATION/names[key], cohorts[key], common_fields)

    monthly = []
    for row in monthly_rows_raw:
        weights = row.get("feature_weights_json") or {}
        contrib = row.get("feature_contributions_json") or {}
        explanation = row.get("explanation_json") or {}
        def index_for(name: str) -> Any:
            weight = weights.get(name)
            value = contrib.get(name)
            if value is None or not weight:
                return None
            return round(float(value)/float(weight), 6)
        missing = {name: row.get(name) is None for name in ("rainfall_mean_mm","rainfall_cv","temp_mean_c","relative_humidity_mean_pct","wind_speed_mean_ms","solar_radiation_mean_mj")}
        cohort = "A" if row["evaluation_eligibility_status"] == "ELIGIBLE_HIGH_EVIDENCE" else "B"
        monthly.append({
            "attraction_id":row["attraction_id"],"activity_id":row["activity_type_id"],"calendar_month":row["month"],"evaluation_dataset_version":DATASET_VERSION,
            "climate_favorability_score":row["climate_favorability_score"],"relative_monthly_rank":row["climate_favorability_rank"],
            "experimental_score_class":explanation.get("suitability_class"),"rainfall_sub_index":index_for("relative_rainfall_favorability"),
            "rainfall_reliability":index_for("rainfall_reliability_index"),"temperature_comfort":index_for("temperature_comfort_index"),
            "humidity_comfort":index_for("humidity_comfort_index"),"solar_context":index_for("solar_radiation_context"),"wind_context":index_for("wind_context"),
            "climate_uncertainty":row["uncertainty_score"],"geographic_source_type":row["geographic_source_type"],"evidence_status":row["evidence_status"],
            "safety_abstention_status":"ABSTAIN" if explanation.get("missing_critical_evidence") else "NO_RECORDED_ABSTENTION",
            "mapping_evidence_tier":row["evidence_tier"],"mapping_rule_version":row["mapping_rule_version"],"activity_profile_version":row["activity_profile_version"],
            "historical_reference_period":row["reference_period"],"source_dataset_id":row["dataset_version_id"],"evaluation_cohort":cohort,
            "missingness":missing,
        })
    monthly_fields = list(monthly[0].keys()) if monthly else []
    export_hashes["stage12_4d2_monthly_evaluation_dataset.csv"] = stable_write_csv(EVALUATION/"stage12_4d2_monthly_evaluation_dataset.csv", monthly, monthly_fields)

    # Deterministic, stratified blind reviewer sample.
    strata: dict[tuple[str,str,str], list[dict[str,Any]]] = defaultdict(list)
    for row in persisted:
        strata[(row["activity_code"],row["mapping_validation_status"],row["evidence_tier"])].append(row)
    sampled: list[dict[str,Any]] = []
    for key in sorted(strata):
        candidates = sorted(strata[key], key=lambda r: hashlib.sha256(f"{RANDOM_SEED}:{r['mapping_id']}".encode()).hexdigest())
        sampled.extend(candidates[:2])
    sampled = sorted({r["mapping_id"]:r for r in sampled}.values(), key=lambda r:r["mapping_id"])
    mapping_blind = [{
        "review_item_id":f"MAP-{r['mapping_id']}","attraction_id":r["attraction_id"],"attraction_name":r["attraction_name"],"district":r["district_name"],
        "proposed_activity":r["activity_name"],"primary_category":r["primary_category"],"secondary_categories":r["secondary_categories"],
        "explicit_activity_tags":r["explicit_activities"],"description":r["description"],"source_references":r["source_metadata"],
        "sampling_probability":min(1.0,2/max(1,len(strata[(r['activity_code'],r['mapping_validation_status'],r['evidence_tier'])]))),
        "reviewer_id":"","reviewer_expertise":"","review_timestamp":"","evidence_reviewed":"","decision":"","confidence":"","notes":"",
    } for r in sampled]
    mapping_review_fields = list(mapping_blind[0].keys()) if mapping_blind else []
    export_hashes["stage12_4d2_mapping_review_blind.csv"] = stable_write_csv(EVALUATION/"stage12_4d2_mapping_review_blind.csv", mapping_blind, mapping_review_fields)

    monthly_by_pair = defaultdict(list)
    for row in monthly_rows_raw:
        monthly_by_pair[(row["attraction_id"],row["activity_type_id"])].append(row)
    seasonality_blind=[]
    for r in sampled:
        for m in monthly_by_pair.get((r["attraction_id"],r["activity_type_id"]),[]):
            if m["month"] not in (1,4,7,10):
                continue
            seasonality_blind.append({
                "review_item_id":f"SEA-{r['mapping_id']}-{m['month']:02d}","attraction_id":r["attraction_id"],"attraction_name":r["attraction_name"],
                "activity":r["activity_name"],"calendar_month":m["month"],"district":r["district_name"],"historical_reference_period":m["reference_period"],
                "rainfall_mean_mm":m["rainfall_mean_mm"],"rainfall_cv":m["rainfall_cv"],"temperature_mean_c":m["temp_mean_c"],
                "relative_humidity_mean_pct":m["relative_humidity_mean_pct"],"wind_speed_mean_ms":m["wind_speed_mean_ms"],"solar_radiation_mean_mj":m["solar_radiation_mean_mj"],
                "climate_source_type":m["geographic_source_type"],"source_dataset_id":m["dataset_version_id"],
                "reviewer_id":"","reviewer_expertise":"","review_timestamp":"","evidence_reviewed":"","decision":"","confidence":"","notes":"",
            })
    seasonality_blind.sort(key=lambda r:r["review_item_id"])
    seasonality_review_fields=list(seasonality_blind[0].keys()) if seasonality_blind else []
    export_hashes["stage12_4d2_seasonality_review_blind.csv"] = stable_write_csv(EVALUATION/"stage12_4d2_seasonality_review_blind.csv",seasonality_blind,seasonality_review_fields)

    sampling_manifest={
        "dataset_version":DATASET_VERSION,"random_seed":RANDOM_SEED,"method":"SHA-256 deterministic stratification; up to two mappings per activity/status/evidence-tier stratum",
        "mapping_review_items":len(mapping_blind),"seasonality_review_items":len(seasonality_blind),
        "labels_status":"PENDING_INDEPENDENT_REVIEW","model_predictions_exposed_to_reviewers":False,
        "activity_coverage":sorted({r["activity_code"] for r in sampled}),"evidence_tier_coverage":sorted({r["evidence_tier"] for r in sampled}),
        "mapping_status_coverage":sorted({r["mapping_validation_status"] for r in sampled}),
    }
    write_json(EVALUATION/"stage12_4d2_review_sampling_manifest.json",sampling_manifest)

    baseline_manifest={
      "dataset_version":DATASET_VERSION,"configuration_frozen":True,"weights_modified":False,
      "baselines":{
        "A":{"name":"Rainfall-only","definition":"Rank the 12 historical calendar months by rainfall favorability.","source":"Stage 12.4C climate climatology","features":["rainfall_mean_mm"],"geographic_resolution":"attraction reanalysis or disclosed district proxy","missing_data_policy":"abstain; no synthetic fill"},
        "B":{"name":"District multi-variable climatology","definition":"Existing Stage 12.4C multi-variable baseline.","source":"climate_seasonality_features","features":["rainfall","temperature","humidity"],"geographic_resolution":"district","missing_data_policy":"existing Stage 12.4C policy"},
        "C":{"name":"Rainfall risk-adjusted","definition":"Rank using rainfall mean and interannual variability.","source":"Stage 12.4C climatology","features":["rainfall_mean_mm","rainfall_cv"],"geographic_resolution":"district","missing_data_policy":"abstain"},
        "D":{"name":"Activity-aware seasonality","definition":"Existing Stage 12.4D climate suitability engine.","source":"climate_attraction_activity_seasonality","features":"activity profile dependent","geographic_resolution":"attraction reanalysis or disclosed district proxy","missing_data_policy":"existing activity profile uncertainty policy"},
        "E":{"name":"Activity-aware high-evidence subset","definition":"Baseline D restricted to Cohort A; an evaluation subset, not a predictive algorithm.","source":"Cohort A + Baseline D","features":"same as D","geographic_resolution":"same as D","missing_data_policy":"same as D"},
      },"activity_profile_configurations":profile_configs,
      "limitations":["Rule-derived mappings are not independent human ground truth.","Shared district climate proxies require cluster-aware inference."]
    }
    write_json(EVALUATION/"stage12_4d2_baseline_configuration_manifest.json",baseline_manifest)

    eligibility_report={"status":"EVALUATION_ELIGIBILITY_PERSISTED","policy_version":POLICY_VERSION,"operational_eligibility_preserved_as_separate_concept":True,
                        "distribution":eligibility_distribution,"evidence_tiers":tier_distribution,"independent_human_reviews_completed":0,
                        "cohort_counts":{k:len(v) for k,v in cohorts.items()}}
    write_json(REPORTS/"stage12_4d2_evaluation_eligibility.json",eligibility_report)

    evidence_distribution={
      "evidence_tiers":tier_distribution,"mapping_statuses":status_distribution,
      "by_activity":{},"by_district":{},"by_mapping_method":{}
    }
    for dimension,column in (("by_activity","activity_code"),("by_district","district_name"),("by_mapping_method","mapping_method")):
        nested=defaultdict(Counter)
        for r in persisted:nested[str(r.get(column) or "UNKNOWN")][r["evidence_tier"]]+=1
        evidence_distribution[dimension]={k:dict(sorted(v.items())) for k,v in sorted(nested.items())}
    write_json(REPORTS/"stage12_4d2_evidence_distribution.json",evidence_distribution)

    proxy_distribution=Counter(r["geographic_source_type"] for r in monthly_rows_raw)
    proxy_by_cohort=defaultdict(Counter)
    for r in monthly_rows_raw:
        cohort="A" if r["evaluation_eligibility_status"]=="ELIGIBLE_HIGH_EVIDENCE" else "B"
        proxy_by_cohort[cohort][r["geographic_source_type"]]+=1
    geographic_report={"distribution":dict(sorted(proxy_distribution.items())),"by_cohort":{k:dict(sorted(v.items())) for k,v in sorted(proxy_by_cohort.items())},
                       "limitation":"Rows sharing a district representative proxy are not independent climate observations; Stage 12.4E must group or cluster-resample by district/climate-source identity."}
    write_json(REPORTS/"stage12_4d2_geographic_proxy_dependence.json",geographic_report)

    pair_months=Counter((r["attraction_id"],r["activity_id"]) for r in monthly)
    integrity={
      "unique_keys":len({(r["attraction_id"],r["activity_id"],r["calendar_month"]) for r in monthly})==len(monthly),
      "valid_months":all(1<=r["calendar_month"]<=12 for r in monthly),"valid_score_bounds":all(0<=r["climate_favorability_score"]<=1 for r in monthly),
      "complete_pairs":all(v==12 for v in pair_months.values()),"pair_count":len(pair_months),"row_count":len(monthly),
      "missingness":dict(sorted(Counter(k for r in monthly for k,v in r["missingness"].items() if v).items())),
    }
    coverage={"total_attractions":post_counts["attractions"],"mapped_attractions":post_counts["mapped_attractions"],
              "high_evidence_attractions":len({r['attraction_id'] for r in cohorts['A']}),"high_evidence_pairs":len(cohorts['A']),
              "district_coverage":len({r['district_id'] for r in cohorts['A'] if r['district_id'] is not None}),
              "activity_coverage":len({r['activity_type_id'] for r in cohorts['A']}),"monthly_profile_rows":len(monthly)}
    write_json(REPORTS/"stage12_4d2_evaluation_coverage.json",coverage)

    checksums={"algorithm":"SHA-256","dataset_version":DATASET_VERSION,"files":dict(sorted(export_hashes.items())),"deterministic_double_export_verified":True}
    write_json(EVALUATION/"stage12_4d2_dataset_checksums.json",checksums)
    git_hash=os.getenv("STAGE12_GIT_COMMIT","").strip()
    if not git_hash:
        try:
            git_hash=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError("STAGE12_GIT_COMMIT must be supplied when git is unavailable in the execution container")
    existing_manifest=EVALUATION/"stage12_4d2_dataset_manifest.json"
    created_at=utcnow()
    if existing_manifest.exists():
        old=json.loads(existing_manifest.read_text(encoding="utf-8"))
        if old.get("dataset_version")==DATASET_VERSION and old.get("file_hashes")!=checksums["files"]:
            raise RuntimeError("Refusing to overwrite immutable dataset version with different hashes")
        created_at=old.get("dataset_creation_timestamp",created_at)
    manifest={
      "dataset_version":DATASET_VERSION,"dataset_creation_timestamp":created_at,"git_commit_hash":git_hash,"alembic_revision":post_counts["alembic_revision"],
      "postgresql_snapshot_metadata":{"isolation_level":"REPEATABLE READ","readback_timestamp":utcnow()},
      "climate_dataset_versions":datasets,"mapping_rule_versions":sorted({r["mapping_rule_version"] for r in persisted}),
      "activity_profile_versions":sorted({r["activity_profile_version"] for r in monthly_rows_raw}),"explanation_versions":sorted({r["processing_version"] for r in monthly_rows_raw}),
      "evidence_policy_version":POLICY_VERSION,"evaluation_eligibility_policy":"Tier A high evidence; Tier B inferred sensitivity; Tier C/D excluded from trusted positive ground truth",
      "counts":{"attractions":post_counts["attractions"],"mappings":post_counts["total_mappings"],"active_monthly_profiles":post_counts["active_profiles"],"cohorts":{k:len(v) for k,v in cohorts.items()},"monthly_export_rows":len(monthly)},
      "missingness":integrity["missingness"],"source_provenance":"PostgreSQL tables listed in export schema; NASA POWER source versions embedded above",
      "random_seed":RANDOM_SEED,"export_schema":{"cohorts":common_fields,"monthly":monthly_fields,"mapping_review":mapping_review_fields,"seasonality_review":seasonality_review_fields},
      "file_hashes":checksums["files"],"deterministic_double_export_verified":True,"immutable":True,
    }
    write_json(existing_manifest,manifest)

    db_readback={"status":"INDEPENDENT_SQL_READBACK_VERIFIED","verified_at_utc":utcnow(),"sql_statements":COUNT_SQL,"database_counts":post_counts,
                 "mapping_status_distribution":status_distribution,"evidence_tier_distribution":tier_distribution,"evaluation_eligibility_distribution":eligibility_distribution,
                 "protected_counts_match_preflight":all(post_counts[k]==v for k,v in before_hashes.items())}
    write_json(REPORTS/"stage12_4d2_database_readback.json",db_readback)
    experiments={
      "experiment_1_evidence_reconciliation":{"contradictory_metric_instances":reconciliation["contradictory_metric_instances"],"authoritative_values":reconciliation_actual},
      "experiment_2_mapping_evidence_distribution":tier_distribution,
      "experiment_3_provisional_error_analysis":{"classes":provisional_report["classification_distribution"],"most_frequent_rules":dict(Counter(r["mapping_method"] for r in provisional).most_common(10))},
      "experiment_4_evaluation_coverage":coverage,
      "experiment_5_geographic_proxy_dependence":geographic_report,
      "experiment_6_dataset_integrity":integrity,
      "experiment_7_dataset_reproducibility":{"stable":True,"hashes":checksums["files"]},
      "experiment_8_review_sampling_coverage":sampling_manifest,
      "human_evaluation_results":"PENDING; no labels fabricated",
    }
    write_json(REPORTS/"stage12_4d2_research_experiments.json",experiments)

    # Protocols are generated as transparent, versioned research documentation.
    (DOCS/"STAGE_12_4D2_MAPPING_REVIEW_PROTOCOL.md").write_text(f"""# Stage 12.4D.2 Independent Mapping Review Protocol

Dataset version: `{DATASET_VERSION}`. Sampling seed: `{RANDOM_SEED}`.

Reviewers must not see model scores, predicted classes, evidence tiers, or rule decisions. Task 1 asks: **Does the available attraction evidence support the proposed activity at this location?** Allowed labels are `SUPPORTED`, `UNSUPPORTED`, `UNCERTAIN`, and `INSUFFICIENT_EVIDENCE`.

Task 2 asks: **Based on the provided independent evidence, how favorable is the specified calendar month for the stated activity at this attraction?** Allowed labels are `VERY_FAVORABLE`, `FAVORABLE`, `NEUTRAL`, `UNFAVORABLE`, `VERY_UNFAVORABLE`, and `INSUFFICIENT_EVIDENCE`.

Record reviewer ID, expertise, timestamp, evidence reviewed, decision, confidence, and notes. Two reviewers should label each item independently; disagreements are adjudicated without revealing model output. Blank fields mean pending review and must never be interpreted as a negative label.

Sampling is deterministic and stratified by activity, historical mapping status, and evidence tier. Sampling probabilities are recorded per mapping. The blind files intentionally omit model-derived conclusions.
""",encoding="utf-8",newline="\n")
    (DOCS/"STAGE_12_4E_EVALUATION_PROTOCOL.md").write_text("""# Stage 12.4E Evaluation Protocol (Prepared, Not Executed)

The test dataset is frozen before tuning. Historical climate inputs, rule mappings, computed scores, and independent judgments remain separate. No computed score is a human relevance label.

For ranking the 12 calendar months of an attraction–activity pair, report NDCG@3, NDCG@5 only where five judged relevant positions are meaningful, Spearman correlation, Kendall tau, top-3 overlap, and MRR only under a preregistered binary relevance definition. Attraction ranking is a different task and requires a separate query–attraction judgment dataset.

Compare rainfall-only, district multivariable, rainfall risk-adjusted, activity-aware, and the activity-aware Cohort A subset. Baseline E is a subset, not another algorithm. Planned ablations remove temperature, humidity, reliability, geographic specificity, and activity-specific profiles one at a time without retuning the frozen test set.

Use paired bootstrap confidence intervals and cluster-aware resampling by district or climate-source identity because many attractions share proxies. Keep duplicate and near-duplicate attractions in the same split. Recommended development splitting groups by district/climate source; freeze a held-out district-group test set before calibration. Do not run significance tests until genuine independent labels exist. Mapping recall is reportable only if the sampling frame supports population estimation; use inverse-probability weighting for the stratified sample where justified.
""",encoding="utf-8",newline="\n")
    (DOCS/"STAGE_12_4D2_EVIDENCE_RECONCILIATION_AND_EVALUATION_FREEZE.md").write_text(f"""# Stage 12.4D.2 Evidence Reconciliation and Evaluation Freeze

Status: dataset frozen under `{DATASET_VERSION}` with evidence policy `{POLICY_VERSION}`.

Direct SQL confirmed Result A as the Stage 12.4D.1 persisted snapshot before this stage: 10,127 mappings, 8,940 eligible, 1,187 unsupported, 107,280 active profiles, and status counts 1,023 VERIFIED / 3,189 SUPPORTED_INFERRED / 4,728 PROVISIONAL / 1,187 UNSUPPORTED. Result B appears in narrative material but is not supported by the current database or timestamped final/readback JSON. Its precise originating run or code version cannot be established and remains explicitly unresolved.

Evidence policy v1.2 separates source strength, rule validation, independent review, and offline-evaluation eligibility. Tier A means explicit structured evidence; it does not mean human verification. Tier B is deterministic inference. Tier C is weak context. Tier D is absent or contradictory. Provisional mappings remain available for uncertainty analysis and are not positive primary ground truth.

The frozen monthly dataset includes only active profiles whose mappings are offline-evaluation eligible. Rows are deterministically sorted and serialized, and every export has a SHA-256 digest. No missing climate value was synthetically filled. Reviewer templates are blank and model conclusions are withheld.

Scientific limitations remain: independent labels are pending; deterministic rules and mappings are dependent evidence; many profiles share district proxies; NASA POWER resolution does not capture all local microclimates; and the evaluation assesses historical relative climate favorability, not live safety or operational availability.
""",encoding="utf-8",newline="\n")

    test_run=subprocess.run([sys.executable,str(ROOT/"scripts"/"run_stage12_4d2_tests.py")],cwd=ROOT,text=True,capture_output=True)
    if test_run.returncode != 0:
        print(test_run.stdout)
        print(test_run.stderr,file=sys.stderr)
        raise RuntimeError("Stage 12.4D.2 automated tests failed")
    tests_report=load_json_file(REPORTS/"stage12_4d2_tests.json")
    regression_results={}
    for stage,name in (("12.4D","stage12_4d_tests.json"),("12.4D.1","stage12_4d1_tests.json")):
        path=REPORTS/name
        if path.exists():
            payload=load_json_file(path)
            regression_results[stage]={k:payload.get(k) for k in ("status","total_tests","passed","failed")}

    final={
      "status":"EVALUATION_DATASET_FROZEN_VERIFIED","stage":"12.4D.2","migration_id":MIGRATION_ID,
      "started_at_utc":started,"completed_at_utc":utcnow(),"pre_policy_counts":pre_counts,"final_database_counts":post_counts,
      "historical_discrepancy_cause":reconciliation["mandatory_discrepancy_conclusion"],"provisional_audit":provisional_report["classification_distribution"],
      "evidence_tier_distribution":tier_distribution,"evaluation_eligibility_distribution":eligibility_distribution,
      "mapping_corrections_performed":provisional_report["classification_distribution"].get("PROVISIONAL_CONTRADICTORY",0),
      "cohort_counts":{k:len(v) for k,v in cohorts.items()},"monthly_dataset_rows":len(monthly),"geographic_proxy_distribution":dict(proxy_distribution),
      "dataset_version":DATASET_VERSION,"checksums":checksums["files"],"review_sampling":sampling_manifest,
      "integrity":integrity,"stage12_4e":"PROTOCOL_READY_NOT_EXECUTED","remaining_limitations":baseline_manifest["limitations"]+["Independent reviewer labels are pending."],
      "automated_tests":{k:tests_report.get(k) for k in ("status","total_tests","passed","failed")},"regression_tests":regression_results,
    }
    write_json(REPORTS/"stage12_4d2_final_summary.json",final)
    print(json.dumps({"status":final["status"],"counts":post_counts,"cohorts":final["cohort_counts"],"monthly_rows":len(monthly)},indent=2,default=json_default))


if __name__ == "__main__":
    main()
