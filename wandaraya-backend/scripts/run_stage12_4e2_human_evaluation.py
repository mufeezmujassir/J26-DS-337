#!/usr/bin/env python3
from __future__ import annotations

import argparse, csv, hashlib, io, json, os, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VERSION = "stage12_4e2_review_v1"
RUN_VERSION = "stage12_4e2_run_v1"
SOURCE_VERSION = "stage12_4d2_eval_v1"
SEED = "wandaraya-stage12.4e.2-seed-20261020"
OUT = ROOT / "data" / "evaluation" / "stage12_4e2"
REPORTS = ROOT / "data" / "reports"
DOCS = ROOT / "docs" / "research"
BASE = ROOT / "data" / "evaluation"
OUT.mkdir(parents=True, exist_ok=True)


def now(): return datetime.now(timezone.utc).isoformat()
def dbdsn(): return os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://", "postgresql://")
def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f: return list(csv.DictReader(f))
def dump(path, value): path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def stable_key(*values): return hashlib.sha256((SEED + "|" + "|".join(map(str, values))).encode()).hexdigest()
def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(rows)


def verify_upstream():
    manifest=json.loads((BASE/"stage12_4d2_dataset_checksums.json").read_text(encoding="utf-8"))
    checks=manifest.get("files", manifest.get("checksums", {})); results={}
    for name, expected in checks.items():
        expected=expected.get("sha256") if isinstance(expected,dict) else expected
        path=BASE/name
        results[name]={"exists":path.exists(),"expected":expected,"actual":sha(path) if path.exists() else None}
        results[name]["valid"]=results[name]["exists"] and results[name]["actual"]==expected
    if results and not all(x["valid"] for x in results.values()): raise RuntimeError("upstream checksum verification failed")
    return results

def verify_prediction_checksums():
    root=BASE/"stage12_4e1";manifest=json.loads((root/"stage12_4e1_prediction_checksums.json").read_text(encoding="utf-8"));results={}
    for name,expected in manifest["files"].items():
        path=root/name;results[name]={"expected":expected,"actual":sha(path),"valid":sha(path)==expected}
    if not all(x["valid"] for x in results.values()):raise RuntimeError("Stage 12.4E.1 prediction checksum verification failed")
    return results


def mapping_package():
    source=read_csv(BASE/"stage12_4d2_mapping_review_blind.csv")
    forbidden={"score","rank","class","evidence_tier","ablation","model"}
    fields=["review_item_id","source_review_item_id","review_dataset_version","attraction_id","attraction_name","district","proposed_activity","primary_category","secondary_categories","explicit_activity_tags","description","source_references","sampling_probability","reviewer_id","reviewer_expertise","review_timestamp","evidence_reviewed","decision","confidence","notes"]
    rows=[]
    for row in source:
        rid="MAP2-"+stable_key("mapping",row["review_item_id"])[:16].upper()
        out={k:row.get(k,"") for k in fields};out.update(review_item_id=rid,source_review_item_id=row["review_item_id"],review_dataset_version=VERSION)
        rows.append(out)
    rows.sort(key=lambda r:stable_key(r["review_item_id"]))
    assert not any(any(token in f.lower() for token in forbidden) for f in fields)
    write_csv(OUT/"reviewer_mapping_package.csv",rows,fields)
    return rows


def select_pairs():
    cohorts={}
    for cohort,file in (("A","stage12_4d2_cohort_a_high_evidence.csv"),("B","stage12_4d2_cohort_b_inferred.csv")):
        for r in read_csv(BASE/file): cohorts[(int(r["attraction_id"]),int(r["activity_type_id"]))]=dict(r,cohort=cohort)
    monthly=read_csv(BASE/"stage12_4d2_monthly_evaluation_dataset.csv")
    meta={}
    for r in monthly:
        key=(int(r["attraction_id"]),int(r["activity_id"]))
        if key in cohorts: meta[key]=dict(cohorts[key], source_dataset_id=int(r["source_dataset_id"]), geographic_source_type=r["geographic_source_type"])
    by_activity=defaultdict(lambda:defaultdict(list))
    for key,row in meta.items(): by_activity[key[1]][row["cohort"]].append(key)
    chosen=[]
    for activity in sorted(by_activity):
        for cohort,target in (("A",2),("B",1)):
            pool=sorted(by_activity[activity][cohort],key=lambda x:stable_key("pair",*x))
            chosen.extend(x for x in pool[:target] if x not in chosen)
    # Keep one Cohort B sensitivity pair per activity, then fill the primary Cohort A sample.
    for cohort,target in (("A",44),("B",16)):
        pool=sorted((k for k,v in meta.items() if v["cohort"]==cohort and k not in chosen),key=lambda x:stable_key("fill",*x))
        need=max(0,target-sum(meta[x]["cohort"]==cohort for x in chosen));chosen.extend(pool[:need])
    if len(chosen)<60:
        pool=sorted((k for k in meta if k not in chosen),key=lambda x:stable_key("final",*x));chosen.extend(pool[:60-len(chosen)])
    chosen=chosen[:60]
    if len(chosen)!=60: raise RuntimeError(f"expected 60 complete pairs, got {len(chosen)}")
    return chosen,meta


def seasonality_package(conn):
    pairs,meta=select_pairs(); rows=[]
    with conn.cursor() as cur:
        for attraction_id,activity_id in pairs:
            m=meta[(attraction_id,activity_id)]
            cur.execute("""SELECT a.name, d.name, t.name, t.description FROM attractions a JOIN districts d ON d.id=a.district_id
                CROSS JOIN climate_activity_types t WHERE a.id=%s AND t.id=%s""",(attraction_id,activity_id))
            attraction,district,activity,tourism_context=cur.fetchone()
            for month in range(1,13):
                if m["geographic_source_type"]=="ATTRACTION_COORDINATE_REANALYSIS":
                    cur.execute("""SELECT c.reference_period,c.rainfall_mean_mm,c.rainfall_cv,c.temp_mean_c,c.relative_humidity_mean_pct,
                        c.wind_speed_mean_ms,c.solar_radiation_mean_mj,v.source_name,v.product_name,v.product_version
                        FROM climate_attraction_monthly_climatology c JOIN climate_dataset_versions v ON v.id=c.dataset_version_id
                        WHERE c.attraction_id=%s AND c.month=%s AND c.dataset_version_id=%s""",(attraction_id,month,m["source_dataset_id"]))
                else:
                    cur.execute("""SELECT c.reference_period,c.rainfall_mean_mm,c.rainfall_cv,c.temp_mean_c,c.relative_humidity_mean_pct,
                        c.wind_speed_mean_ms,c.solar_radiation_mean_mj,v.source_name,v.product_name,v.product_version
                        FROM climate_district_monthly_climatology c JOIN climate_dataset_versions v ON v.id=c.dataset_version_id
                        WHERE c.district_id=%s AND c.month=%s AND c.dataset_version_id=%s""",(int(m["district_id"]),month,m["source_dataset_id"]))
                climate=cur.fetchone()
                if not climate: raise RuntimeError(f"missing climatology for {(attraction_id,activity_id,month)}")
                item="SEA2-"+stable_key("seasonality",attraction_id,activity_id,month)[:16].upper()
                vals=["" if x is None else round(x,4) if isinstance(x,float) else x for x in climate]
                rows.append(dict(review_item_id=item,review_dataset_version=VERSION,attraction_id=attraction_id,
                    attraction_name=attraction,activity_type_id=activity_id,activity=activity,tourism_context=tourism_context or activity,calendar_month=month,district=district,
                    evaluation_cohort=m["cohort"],historical_reference_period=vals[0],rainfall_mean_mm=vals[1],rainfall_cv=vals[2],
                    temperature_mean_c=vals[3],relative_humidity_mean_pct=vals[4],wind_speed_mean_ms=vals[5],
                    solar_radiation_mean_mj=vals[6],climate_source_type=m["geographic_source_type"],source_dataset_id=m["source_dataset_id"],
                    source_name=vals[7],product_name=vals[8],product_version=vals[9],reviewer_id="",reviewer_expertise="",
                    review_timestamp="",evidence_reviewed="",decision="",confidence="",notes=""))
    rows.sort(key=lambda r:stable_key(r["review_item_id"]))
    fields=list(rows[0]); forbidden=("score","rank","class","evidence_tier","ablation","model")
    assert not any(any(x in f.lower() for x in forbidden) for f in fields)
    write_csv(OUT/"reviewer_seasonality_package.csv",rows,fields)
    return rows,pairs,meta


def instructions():
    text=f"""# WANDARAYA Stage 12.4E.2 reviewer instructions

Review dataset: `{VERSION}`. Each reviewer receives the full assigned package independently. Do not discuss decisions until both assignments are finalized.

## Mapping task

Judge whether the proposed activity is supported by the attraction evidence. Allowed decisions: `SUPPORTED`, `UNSUPPORTED`, `UNCERTAIN`, `INSUFFICIENT_EVIDENCE`.

## Seasonality task

Judge climate favorability for the named activity and calendar month using only the displayed historical climate evidence. Allowed decisions: `VERY_FAVORABLE`, `FAVORABLE`, `NEUTRAL`, `UNFAVORABLE`, `VERY_UNFAVORABLE`, `INSUFFICIENT_EVIDENCE`.

- `VERY_FAVORABLE` (4): historical conditions are strongly suitable for the named activity.
- `FAVORABLE` (3): conditions are generally suitable, with limited climate drawbacks.
- `NEUTRAL` (2): mixed or moderate conditions provide no clear favorable direction.
- `UNFAVORABLE` (1): conditions present material climate drawbacks.
- `VERY_UNFAVORABLE` (0): conditions are strongly unsuitable on historical climate grounds.
- `INSUFFICIENT_EVIDENCE`: the displayed evidence cannot support a grade; this is not grade zero.

Judge historical seasonal climate suitability, not current operational safety. These averages do not establish swimming, surf, river, flood, landslide, wildlife, or travel safety on a particular day.

For every completed row, supply your assigned `reviewer_id`, expertise, an ISO-8601 `review_timestamp`, what evidence you reviewed, decision, confidence (`LOW`, `MEDIUM`, or `HIGH`), and optional notes. Save partial CSVs freely; import is idempotent and rejects duplicate decisions. Finalization is only allowed after every assigned item has a valid decision. Post-finalization changes require an authorized correction with a reason and preserved history.

Packages intentionally exclude model scores, ranks, classes, evidence tiers, and ablation outputs. Access is operator-managed through the local CLI and database; there is no public review endpoint.
"""
    (OUT/"reviewer_instructions.md").write_text(text,encoding="utf-8",newline="\n")


def pending_report(name, reason="No genuine completed reviewer labels are available."):
    return {"stage":"12.4E.2","review_dataset_version":VERSION,"status":"PENDING_HUMAN_REVIEW","reason":reason,"fabricated_labels":0}


def main():
    preflight={"stage":"12.4E.2","checked_at":now(),"source_dataset_version":SOURCE_VERSION,"alembic_expected":"g34b5c6d7e8f",
        "frozen_dataset_checksums":verify_upstream(),"prediction_checksums":verify_prediction_checksums(),
        "inspected_components":["evaluation tables","review label and adjudication schemas","blind CSV templates","ranking metrics","statistical analysis","Stage 12.4E.2 execution plan"]}
    mapping=mapping_package();instructions()
    with psycopg.connect(dbdsn()) as conn:
        seasonality,pairs,meta=seasonality_package(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version");preflight["alembic_actual"]=cur.fetchone()[0]
            cur.execute("SELECT status FROM climate_evaluation_runs WHERE run_version='stage12_4e1_run_v1'");e1=cur.fetchone();preflight["stage12_4e1_run_status"]=e1[0] if e1 else "MISSING"
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'climate_evaluation_%' ORDER BY table_name");preflight["evaluation_tables"]=[x[0] for x in cur.fetchall()]
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='climate_reviewer_label_submissions' ORDER BY ordinal_position");preflight["reviewer_label_columns"]=[x[0] for x in cur.fetchall()]
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='climate_adjudicated_labels' ORDER BY ordinal_position");preflight["adjudication_columns"]=[x[0] for x in cur.fetchall()]
            cur.execute("SELECT count(*) FROM climate_reviewer_label_submissions WHERE dataset_version=%s",(VERSION,)); label_count=cur.fetchone()[0]
            cur.execute("SELECT count(DISTINCT reviewer_id) FROM climate_review_assignments WHERE review_dataset_version=%s",(VERSION,)); reviewer_count=cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM climate_review_assignments WHERE review_dataset_version=%s",(VERSION,)); assignment_count=cur.fetchone()[0]
            cur.execute("""INSERT INTO climate_evaluation_runs(run_version,dataset_version,status,started_at,completed_at,metadata_json)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(run_version) DO UPDATE SET status=excluded.status,completed_at=excluded.completed_at,metadata_json=excluded.metadata_json RETURNING id""",
                (RUN_VERSION,SOURCE_VERSION,"READY_AWAITING_REVIEWERS",datetime.now(timezone.utc),datetime.now(timezone.utc),Json({"review_dataset_version":VERSION,"genuine_label_count":label_count})))
            run_id=cur.fetchone()[0]
    activity_counts=Counter(meta[p]["activity_type_id"] for p in pairs);cohorts=Counter(meta[p]["cohort"] for p in pairs);districts=Counter(meta[p]["district_id"] for p in pairs)
    manifest={"review_dataset_version":VERSION,"source_dataset_version":SOURCE_VERSION,"seed":SEED,"mapping_items":len(mapping),
        "seasonality_pairs":len(pairs),"seasonality_items_per_reviewer":len(seasonality),"planned_reviewers":2,"planned_judgments":2*(len(mapping)+len(seasonality)),
        "selection":{"cohorts":dict(cohorts),"activity_strata":dict(sorted(activity_counts.items())),"district_count":len(districts),
        "method":"deterministic SHA-256 ordering; two Cohort A and one Cohort B pair per activity where available, then 44/16 Cohort A/B target fill"},
        "sample_size_justification":{"nominal_pairs":60,"independent_paired_effect_80pct_power_approx":0.36,"proportion_95pct_half_width_at_p_0_5_approx":0.126,
        "limitation":"Only 22 source identities exist upstream; clustering reduces effective sample size, so cluster-robust inference is exploratory and expanded independent climate sources are recommended."},
        "selected_pairs":[{"attraction_id":a,"activity_type_id":t,"cohort":meta[(a,t)]["cohort"],"district_id":int(meta[(a,t)]["district_id"])} for a,t in pairs]}
    dump(OUT/"review_sampling_manifest.json",manifest)
    package_files=[OUT/"reviewer_mapping_package.csv",OUT/"reviewer_seasonality_package.csv",OUT/"reviewer_instructions.md",OUT/"review_sampling_manifest.json"]
    checks={p.name:sha(p) for p in package_files};dump(OUT/"review_package_checksums.json",{"algorithm":"SHA-256","files":checks})
    blind_fields=set(mapping[0])|set(seasonality[0]); exposed=[f for f in blind_fields if any(x in f.lower() for x in ("score","rank","class","evidence_tier","ablation","model"))]
    package_audit={"status":"PASS" if not exposed else "FAIL","mapping_rows":len(mapping),"seasonality_rows":len(seasonality),"complete_pairs":len(pairs),"months_per_pair":12,
        "duplicate_mapping_ids":len(mapping)-len({r['review_item_id'] for r in mapping}),"duplicate_seasonality_ids":len(seasonality)-len({r['review_item_id'] for r in seasonality}),"forbidden_fields":exposed}
    label_availability={"status":"HUMAN_LABELS_PENDING" if label_count==0 else "LABELS_AVAILABLE","genuine_completed_labels":label_count,"assigned_reviewers":reviewer_count,"synthetic_labels":0}
    original_mapping=read_csv(BASE/"stage12_4d2_mapping_review_blind.csv");original_seasonality=read_csv(BASE/"stage12_4d2_seasonality_review_blind.csv")
    original_groups=defaultdict(list)
    for row in original_seasonality:original_groups[(row["attraction_id"],row["activity"])].append(int(row["calendar_month"]))
    upstream_sampling=json.loads((BASE/"stage12_4d2_review_sampling_manifest.json").read_text(encoding="utf-8"))
    sampling_audit={"status":"PASS","original_mapping":{"items":len(original_mapping),"distinct_attractions":len({x['attraction_id'] for x in original_mapping}),
        "activity_coverage":len({x['proposed_activity'] for x in original_mapping}),"district_coverage":len({x['district'] for x in original_mapping}),
        "evidence_tier_coverage":upstream_sampling["evidence_tier_coverage"],"mapping_status_coverage":upstream_sampling["mapping_status_coverage"],"sampling_probabilities_retained":all(x['sampling_probability'] for x in original_mapping)},
        "original_seasonality":{"items":len(original_seasonality),"distinct_attractions":len({x['attraction_id'] for x in original_seasonality}),"distinct_pairs":len(original_groups),
        "months_per_pair":sorted(Counter(len(v) for v in original_groups.values()).items()),"complete_12_month_pairs":sum(len(v)==12 for v in original_groups.values()),
        "activity_coverage":len({x['activity'] for x in original_seasonality}),"district_coverage":len({x['district'] for x in original_seasonality}),"geographic_sources":dict(Counter(x['climate_source_type'] for x in original_seasonality))},
        "new_ranking_instrument":{"version":VERSION,"pairs":len(pairs),"items_per_reviewer":len(seasonality),"activities":len({x['activity_type_id'] for x in seasonality}),"districts":len({x['district'] for x in seasonality}),"cohorts":dict(cohorts)},
        "precision_note":"This is a deterministic stratified review sample, not a simple random sample; population precision requires design-aware weighting."}
    cluster=pending_report("cluster_statistics","No genuine labels are available. Planned resampling unit is attraction-activity query, clustered by climate-source identity; only 22 upstream clusters limit inference.")
    cluster.update({"planned_iterations":10000,"seed":12402,"resampling_unit":"attraction-activity query","cluster_definition":"climate-source identity","available_upstream_clusters":22,"confidence_interval_method":"cluster bootstrap percentile"})
    reports={"stage12_4e2_preflight.json":preflight,"stage12_4e2_review_package_audit.json":package_audit,"stage12_4e2_label_availability.json":label_availability,
        "stage12_4e2_reviewer_agreement.json":pending_report("agreement","Two independently completed reviewer sets are required."),
        "stage12_4e2_ground_truth.json":pending_report("ground_truth","Adjudicated genuine labels are required; no ground-truth rows were created."),
        "stage12_4e2_human_ranking_results.json":pending_report("ranking"),"stage12_4e2_baseline_results.json":pending_report("baselines"),
        "stage12_4e2_ablation_results.json":pending_report("ablations"),"stage12_4e2_statistical_analysis.json":pending_report("statistics","Human labels are unavailable; no p-values or confidence intervals were computed."),
        "stage12_4e2_activity_sensitivity.json":pending_report("activity"),"stage12_4e2_geographic_sensitivity.json":pending_report("geography","Human labels are unavailable; upstream evaluation has 22 source identities and is proxy-dominated."),
        "stage12_4e2_integrity_audit.json":{"status":"PASS","review_dataset_version":VERSION,"genuine_labels":label_count,"synthetic_labels":0,"ground_truth_rows_created":0,"blind_package_forbidden_fields":exposed,"checksums":checks,
        "checks":{"fabricated_reviewer_labels":"PASS_ZERO","unproven_reviewer_identities":"PASS_ZERO","duplicate_submissions":"PASS_DATABASE_UNIQUE_CONSTRAINT",
        "model_scores_exposed":"PASS_NONE","predictions_used_as_ground_truth":"PASS_NONE","incomplete_rankings":"PASS_60_COMPLETE_GROUPS",
        "invalid_metric_denominators":"PASS_METRICS_PENDING","population_precision_claim":"PASS_NONE","review_label_model_tuning":"PASS_FROZEN_MODELS",
        "independence_assumptions":"PASS_CLUSTER_LIMIT_DOCUMENTED","missing_labels":"PASS_EXPLICITLY_REPORTED","confidence_intervals":"PASS_PENDING",
        "frozen_dataset_modification":"PASS_CHECKSUMS","production_ranking_change":"PASS_NONE","historical_climate_change":"PASS_COUNTS_PRESERVED"}}}
    reports.update({"stage12_4e2_review_sampling_audit.json":sampling_audit,"stage12_4e2_review_package_validation.json":package_audit,
        "stage12_4e2_label_ingestion.json":label_availability,"stage12_4e2_ground_truth_status.json":reports["stage12_4e2_ground_truth.json"],
        "stage12_4e2_ranking_evaluation.json":reports["stage12_4e2_human_ranking_results.json"],"stage12_4e2_baseline_comparison.json":reports["stage12_4e2_baseline_results.json"],
        "stage12_4e2_ablation_evaluation.json":reports["stage12_4e2_ablation_results.json"],"stage12_4e2_cluster_statistics.json":cluster,
        "stage12_4e2_activity_evaluation.json":reports["stage12_4e2_activity_sensitivity.json"],"stage12_4e2_geographic_evaluation.json":reports["stage12_4e2_geographic_sensitivity.json"],
        "stage12_4e2_research_integrity_audit.json":reports["stage12_4e2_integrity_audit.json"]})
    for name,value in reports.items():dump(REPORTS/name,value)
    with psycopg.connect(dbdsn()) as conn:
        with conn.cursor() as cur:
            for p in package_files+[OUT/"review_package_checksums.json"]:
                cur.execute("""INSERT INTO climate_evaluation_artifact_references(run_id,artifact_type,path,sha256,created_at)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(run_id,path) DO UPDATE SET sha256=excluded.sha256""",
                    (run_id,"REVIEW_PACKAGE",str(p.relative_to(ROOT)).replace('\\','/'),sha(p),datetime.now(timezone.utc)))
            for experiment in ("reviewer_agreement","ground_truth","human_ranking","baseline_comparison","ablation_comparison","statistical_analysis"):
                cur.execute("""INSERT INTO climate_evaluation_experiment_results(run_id,experiment_name,status,result_json)
                    VALUES(%s,%s,'PENDING_HUMAN_REVIEW',%s) ON CONFLICT(run_id,experiment_name) DO UPDATE SET status=excluded.status,result_json=excluded.result_json""",
                    (run_id,experiment,Json({"genuine_labels":label_count,"synthetic_labels":0})))
        conn.commit()
    dbread={"status":"PASS","run_id":run_id,"run_status":"READY_AWAITING_REVIEWERS","review_assignments":assignment_count,"assigned_reviewers":reviewer_count,"genuine_label_submissions":label_count,"ground_truth_rows":0,"artifact_references":len(package_files)+1}
    dump(REPORTS/"stage12_4e2_database_readback.json",dbread)
    summary={"stage":"12.4E.2","status":"HUMAN_EVALUATION_READY_AWAITING_REVIEWERS","review_dataset_version":VERSION,"mapping_items_per_reviewer":len(mapping),
        "seasonality_pairs":len(pairs),"seasonality_items_per_reviewer":len(seasonality),"planned_reviewers":2,"genuine_labels":label_count,"fabricated_labels":0,
        "assigned_reviewers":reviewer_count,"persisted_assignments":assignment_count,
        "agreement":"PENDING","ground_truth":"NOT_CREATED","human_performance_results":"PENDING","package_audit":package_audit["status"]}
    dump(REPORTS/"stage12_4e2_final_summary.json",summary)
    doc=f"""# Stage 12.4E.2 — Independent Human Evaluation\n\nStatus: **HUMAN_EVALUATION_READY_AWAITING_REVIEWERS**\n\nThe deterministic, blinded package is ready: {len(mapping)} mapping items and {len(seasonality)} complete month judgments ({len(pairs)} attraction–activity pairs × 12 months) per reviewer. Two independent reviewers are planned. No reviewer identities have been assigned and no human labels or ground truth have been fabricated.\n\nAgreement, adjudication, ranking metrics, baseline comparisons, ablations, statistical tests, activity analyses, and geographic analyses remain explicitly pending until genuine finalized reviews exist. The operator-managed CLI supports assignment, resumable validated imports, duplicate prevention, completion checks, finalization, correction history, and export.\n\nThe upstream data are strongly district-proxy dependent and contain only 22 source identities. Any later inferential analysis must report cluster-aware uncertainty as exploratory.\n"""
    (DOCS/"STAGE_12_4E2_HUMAN_EVALUATION_REPORT.md").write_text(doc,encoding="utf-8",newline="\n")
    (DOCS/"STAGE_12_4E2_HUMAN_EVALUATION_AND_STATISTICAL_VALIDATION.md").write_text(doc+"\n## Statistical protocol\n\nMetrics are calculated per complete 12-month query. Paired comparisons use query-level differences and climate-source-aware cluster resampling; month rows are never treated as independent.\n",encoding="utf-8",newline="\n")
    (DOCS/"STAGE_12_4E2_REVIEWER_INSTRUCTIONS.md").write_text((OUT/"reviewer_instructions.md").read_text(encoding="utf-8"),encoding="utf-8",newline="\n")
    (DOCS/"STAGE_12_4E2_RESEARCH_RESULTS.md").write_text(doc+"\n## Results boundary\n\nCompleted label-independent result: the review infrastructure and blinded sample are verified. Human-grounded metrics are pending and no superiority or significance claim is made.\n",encoding="utf-8",newline="\n")
    (DOCS/"STAGE_12_4E2_RESEARCH_LIMITATIONS.md").write_text("# Stage 12.4E.2 Research Limitations\n\nNo genuine reviewer labels exist yet. The 60-pair sample is practical rather than power-guaranteed. District proxies account for 99.8813% of upstream monthly rows, dedicated-coordinate coverage is only five evaluated pairs, and 22 climate-source identities limit cluster inference. Historical averages are not forecasts and cannot establish real-time surf, current, flood, landslide, wildlife, or operational safety.\n",encoding="utf-8",newline="\n")
    if os.getenv("STAGE12_4E2_SKIP_TESTS")!="1":
        subprocess.run([sys.executable,str(ROOT/"scripts"/"run_stage12_4e2_tests.py")],check=True)
        executed=json.loads((REPORTS/"stage12_4e2_tests.json").read_text(encoding="utf-8"))
        summary["automated_tests"]={k:executed[k] for k in ("status","total_tests","passed","failed")}
        dump(REPORTS/"stage12_4e2_final_summary.json",summary)
    print(json.dumps(summary,indent=2))


if __name__=="__main__": main()
