"""Validate human labels and evaluate fixed Stage 12.3D.4 candidate pools."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
from collections import defaultdict
from app.recommendation.evaluation.holiday_event_stage12_3d4 import combined_score, context_score_for_weights, ranking_metrics, select_development_weights, validate_human_annotations, weighted_kappa

ROOT = Path("data/reports")
def write(name, body): (ROOT / name).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--reviewer-1", default=str(ROOT / "stage12_3d4_r1_blind_template.csv")); parser.add_argument("--reviewer-2", default=str(ROOT / "stage12_3d4_r2_blind_template.csv")); parser.add_argument("--universe", default=str(ROOT / "stage12_3d4_candidate_universe_private.json")); parser.add_argument("--adjudications", default=str(ROOT / "stage12_3d4_adjudication_template.csv")); args=parser.parse_args()
    universe=json.loads(Path(args.universe).read_text(encoding="utf-8"))["records"]
    known={(str(x["query_id"]), str(x["attraction_id"])) for x in universe}; rows=[]
    for path in (args.reviewer_1,args.reviewer_2): rows.extend(csv.DictReader(Path(path).open(encoding="utf-8", newline="")))
    synthetic_rows = [row for row in rows if "SYNTHETIC" in str(row.get("annotation_provenance", "")).upper()]
    if synthetic_rows:
        rejected={"status":"AWAITING_INDEPENDENT_HUMAN_LABELS","reason":"Synthetic test fixtures were supplied and are rejected for research metrics/calibration.","synthetic_rows_rejected":len(synthetic_rows),"postgresql_writes":False,"qdrant_writes":False,"production_ranking_changed":False}
        write("stage12_3d4_annotation_quality.json",rejected)
        for name in ("stage12_3d4_baseline_comparison.json","stage12_3d4_weight_calibration.json","stage12_3d4_ablation_results.json","stage12_3d4_final_summary.json"): write(name,rejected)
        write("stage12_3d4_regression_safety.json",{"status":"SAFE","synthetic_labels_rejected":True,"production_ranking_changed":False,"postgresql_writes":False,"qdrant_writes":False})
        print(json.dumps(rejected,indent=2)); return
    checked=validate_human_annotations(rows, known); reviewer_ids=sorted({str(x.get("reviewer_id", "")) for x in rows})
    adjudications={}
    adjudication_path=Path(args.adjudications)
    if adjudication_path.exists():
        for entry in csv.DictReader(adjudication_path.open(encoding="utf-8", newline="")):
            value=str(entry.get("adjudicated_relevance_0_to_3", "")).strip()
            adjudicator=str(entry.get("adjudicator_id", "")).strip()
            reason=str(entry.get("adjudication_reason", "")).strip()
            if value in {"0", "1", "2", "3"} and adjudicator and reason:
                adjudications[(entry["query_id"], str(entry["attraction_id"]))]=int(value)
    disagreements=[]; grouped=defaultdict(list)
    for row in checked["valid"]:
        if not row["cannot_judge"]: grouped[(row["query_id"],str(row["attraction_id"]))].append(row)
    for key, values in grouped.items():
        if len(values)==2 and values[0]["relevance_0_to_3"] != values[1]["relevance_0_to_3"] and key not in adjudications: disagreements.append({"query_id":key[0],"attraction_id":key[1],"scores":{x["reviewer_id"]:x["relevance_0_to_3"] for x in values},"requires_manual_adjudication":True})
    complete=reviewer_ids==["R1","R2"] and not checked["invalid"] and not checked["missing"] and not checked["duplicates"] and not disagreements
    quality={"status":"LABELS_READY_FOR_EVALUATION" if complete else "AWAITING_INDEPENDENT_HUMAN_LABELS", "reviewer_ids":reviewer_ids,"valid_annotations":len(checked["valid"]),"invalid_count":len(checked["invalid"]),"invalid_sample":checked["invalid"][:20],"missing_count":len(checked["missing"]),"missing_sample":checked["missing"][:20],"duplicate_count":len(checked["duplicates"]),"duplicate_sample":checked["duplicates"][:20],"disagreement_count":len(disagreements),"disagreement_sample":disagreements[:20],"resolved_adjudications":len(adjudications),"weighted_cohens_kappa":weighted_kappa(checked["valid"],"R1","R2"),"interpretation":"Kappa is descriptive; small or nonrepresentative samples should not be generalized.","raw_annotations_immutable":True,"postgresql_writes":False,"qdrant_writes":False,"production_ranking_changed":False}
    write("stage12_3d4_annotation_quality.json", quality)
    if not complete:
        label_state = "no complete human label set is available" if not checked["valid"] else "labels are structurally valid; reviewer provenance must be retained outside the tool"
        pending={"status":"AWAITING_INDEPENDENT_HUMAN_LABELS","reason":"Metrics/calibration withheld until complete independent labels are supplied and disagreements are manually adjudicated.","reviewer_ids":reviewer_ids,"valid_annotations":len(checked["valid"]),"missing_labels":len(checked["missing"]),"invalid_labels":len(checked["invalid"]),"duplicate_labels":len(checked["duplicates"]),"disagreements_requiring_adjudication":len(disagreements),"label_state":label_state,"candidate_data_provenance":"real database candidates; manually authored research scenarios","postgresql_writes":False,"qdrant_writes":False,"production_ranking_changed":False}
        # Latency is measured during candidate preparation; label validation
        # must not overwrite that real read-only measurement with a placeholder.
        for name in ("stage12_3d4_baseline_comparison.json","stage12_3d4_weight_calibration.json","stage12_3d4_ablation_results.json","stage12_3d4_final_summary.json"): write(name,pending)
        write("stage12_3d4_regression_safety.json",{"status":"SAFE","production_ranking_changed":False,"postgresql_writes":False,"qdrant_writes":False,"candidate_event_boost":"excluded unless verification_status=verified"}); print(json.dumps(pending,indent=2)); return
    # Consensus is intentionally only usable after manual adjudication; labels agree here.
    labels={(x["query_id"],str(x["attraction_id"])):x["relevance_0_to_3"] for x in checked["valid"] if x["reviewer_id"]=="R1" and not x["cannot_judge"]}
    labels.update(adjudications)
    per_query={}
    for query_id in sorted({x["query_id"] for x in universe}):
        rows_for_query=[x for x in universe if x["query_id"]==query_id]; judged={str(x["attraction_id"]):labels[(query_id,str(x["attraction_id"]))] for x in rows_for_query if (query_id,str(x["attraction_id"])) in labels}
        policies={"baseline":sorted(rows_for_query,key=lambda x:(-x["baseline_score"],x["attraction_id"])),"holiday_event_context":sorted(rows_for_query,key=lambda x:(-combined_score(x["baseline_score"],x["context_score"]),x["attraction_id"])),"poya_only":sorted(rows_for_query,key=lambda x:(-combined_score(x["baseline_score"], x["context_score"] if "poya" in x["context_eligible_features"] else None),x["attraction_id"])),"interest_only":sorted(rows_for_query,key=lambda x:(-combined_score(x["baseline_score"], x["context_score"] if "interests" in x["context_eligible_features"] else None),x["attraction_id"]))}
        per_query[query_id]={name:{**ranking_metrics([str(x["attraction_id"]) for x in ranking],judged,5),**ranking_metrics([str(x["attraction_id"]) for x in ranking],judged,10)} for name,ranking in policies.items()}
    comparison={"status":"OFFLINE_EVALUATION_COMPLETED","method":"same fixed candidate pools; missing context retains baseline score; relevance threshold >=2; recall judged-pool only","per_query":per_query,"postgresql_writes":False,"qdrant_writes":False,"production_ranking_changed":False}
    query_dataset=json.loads((ROOT / "stage12_3d4_query_dataset.json").read_text(encoding="utf-8")); calibration=select_development_weights(universe,labels,query_dataset["split"])
    if calibration["selected"]:
        frozen=calibration["selected"]["weights"]; held=[]
        for query_id in sorted({x["query_id"] for x in universe if query_dataset["split"].get(x["query_id"]) == "held_out"}):
            items=[x for x in universe if x["query_id"]==query_id]; relevant={str(x["attraction_id"]):labels[(query_id,str(x["attraction_id"]))] for x in items if (query_id,str(x["attraction_id"])) in labels}
            if relevant: held.append(ranking_metrics([str(x["attraction_id"]) for x in sorted(items,key=lambda x:(-combined_score(x["baseline_score"],context_score_for_weights(x.get("context_components",{}),frozen)),x["attraction_id"]))],relevant,5))
        held_values=[x["ndcg_at_5"] for x in held if x["ndcg_at_5"] is not None]
        calibration.update({"status":"CALIBRATION_COMPLETED_NOT_GENERALIZABLE","original_heuristic_weights":{"holiday":.2,"poya":.35,"verified_event":.25,"interests":.2},"held_out_query_count":len(held),"held_out_mean_ndcg_at_5":None if not held_values else round(sum(held_values)/len(held_values),6),"warning":"Small manually authored scenario samples cannot establish optimal production weights."})
    write("stage12_3d4_baseline_comparison.json",comparison); write("stage12_3d4_weight_calibration.json",calibration); write("stage12_3d4_ablation_results.json",{"status":"OFFLINE_EVALUATION_COMPLETED","note":"Verified-event ablation is untestable with zero verified links; candidate-only links receive no boost.","per_query":per_query,"postgresql_writes":False,"qdrant_writes":False,"production_ranking_changed":False}); write("stage12_3d4_regression_safety.json",{"status":"SAFE","production_ranking_changed":False,"postgresql_writes":False,"qdrant_writes":False,"candidate_event_boost":"excluded unless verification_status=verified"}); write("stage12_3d4_final_summary.json",{"status":"CONTEXT_WEIGHT_CALIBRATION_VERIFIED" if calibration.get("selected") else "OFFLINE_EVALUATION_COMPLETED","limitations":["manually authored research queries","judged-pool recall only","no verified event links","calibration uses a coarse development-only grid"],"postgresql_writes":False,"qdrant_writes":False,"production_ranking_changed":False}); print(json.dumps({"status":"OFFLINE_EVALUATION_COMPLETED","queries":len(per_query)},indent=2))
if __name__=="__main__": main()
