#!/usr/bin/env python3
"""Run the frozen analysis only after complete genuine review provenance exists."""
from __future__ import annotations
import csv,json,os,sys
from collections import defaultdict
from pathlib import Path
import psycopg

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.climate.evaluation.prospective import DATASET_VERSION
from app.climate.evaluation.prospective_evaluator import validate_protocol,evaluate_verified_rows

OUT=ROOT/"data"/"evaluation"/"stage12_4g";REPORT=ROOT/"data"/"reports"/"stage12_4g_prospective_validation_status.json"
def dsn():return os.getenv("DATABASE_URL","postgresql+psycopg://postgres:root@localhost:5432/wandaraya").replace("postgresql+psycopg://","postgresql://")
def main():
 protocol=validate_protocol(OUT/"prospective_protocol_manifest.json")
 with (OUT/"prospective_reviewer_template.csv").open(encoding="utf-8-sig",newline="") as f:template={r["review_item_id"]:r for r in csv.DictReader(f)}
 historical=set()
 with (ROOT/"data"/"evaluation"/"stage12_4e2"/"stage12_4e2_ground_truth_v1.csv").open(encoding="utf-8",newline="") as f:
  historical={(int(r["attraction_id"]),int(r["activity_id"])) for r in csv.DictReader(f)}
 if any((int(r["attraction_id"]),int(r["activity_type_id"])) in historical for r in template.values()):raise RuntimeError("prohibited Stage 12.4E.2 query overlap")
 with psycopg.connect(dsn()) as conn:
  configs=dict(conn.execute("SELECT model_identifier,configuration_hash FROM climate_evaluation_model_configurations WHERE model_identifier IN ('activity_aware','district_multivariable')").fetchall())
  if configs.get("activity_aware")!=protocol["primary_candidate"]["configuration_hash"] or configs.get("district_multivariable")!=protocol["primary_baseline"]["configuration_hash"]:raise RuntimeError("frozen model configuration hash mismatch")
  reviewers=conn.execute("SELECT DISTINCT reviewer_id FROM climate_review_assignments WHERE review_dataset_version=%s AND status='FINALIZED'",(DATASET_VERSION,)).fetchall()
  submissions=conn.execute("SELECT review_item_id,reviewer_id,label FROM climate_reviewer_label_submissions WHERE dataset_version=%s",(DATASET_VERSION,)).fetchall()
  adjudications=dict(conn.execute("SELECT review_item_id,label FROM climate_adjudicated_labels WHERE dataset_version=%s",(DATASET_VERSION,)).fetchall())
  if not submissions:
   result={"status":"PROSPECTIVE_VALIDATION_PENDING","decision":"PENDING_INDEPENDENT_EVIDENCE","protocol_hash_valid":True,"model_hashes_valid":True,"human_judgments":0,"prospective_metrics":None,"statistical_significance":None,"model_approved":False}
  else:
   if len(reviewers)!=2:result={"status":"PROSPECTIVE_LABELS_INCOMPLETE","decision":"PENDING_INDEPENDENT_EVIDENCE","reason":"exactly two finalized reviewers required","human_judgments":len(submissions),"prospective_metrics":None,"model_approved":False}
   else:
    by=defaultdict(list)
    for item,reviewer,label in submissions:by[item].append((reviewer,label))
    incomplete=[item for item in template if len(by[item])!=2]
    disagreements=[item for item,v in by.items() if len(v)==2 and v[0][1]!=v[1][1]]
    if incomplete or any(item not in adjudications for item in disagreements):
     result={"status":"PROSPECTIVE_LABELS_INCOMPLETE","decision":"PENDING_INDEPENDENT_EVIDENCE","human_judgments":len(submissions),"missing_double_reviews":len(incomplete),"missing_adjudications":sum(i not in adjudications for i in disagreements),"prospective_metrics":None,"model_approved":False}
    else:
     keys=[(int(r["attraction_id"]),int(r["activity_type_id"]),int(r["calendar_month"])) for r in template.values()]
     scores={}
     for attraction,activity,month in keys:
      row=conn.execute("""SELECT p.climate_favorability_score,f.baseline_b_multivar_score FROM climate_attraction_activity_seasonality p JOIN climate_seasonality_features f ON f.district_id=p.district_id AND f.dataset_version_id=p.dataset_version_id AND f.month=p.month AND f.feature_version='12.4c_v1' WHERE p.attraction_id=%s AND p.activity_type_id=%s AND p.month=%s AND p.is_active=true""",(attraction,activity,month)).fetchone()
      scores[(attraction,activity,month)]=row
     rows=[]
     for item,meta in template.items():
      labels=by[item];final=labels[0][1] if labels[0][1]==labels[1][1] else adjudications[item]
      key=(int(meta["attraction_id"]),int(meta["activity_type_id"]),int(meta["calendar_month"]));candidate,baseline=scores[key]
      rows.append({**meta,"evaluation_query_id":f"{key[0]}:{key[1]}","final_decision":final,"candidate_score":candidate,"baseline_score":baseline,"geographic_evidence_level":meta["climate_source_type"]})
     result=evaluate_verified_rows(rows);result.update(protocol_hash_valid=True,model_hashes_valid=True,human_judgments=len(submissions),model_approved=result["decision"]=="SUPPORTED_IMPROVEMENT")
 REPORT.write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8",newline="\n");print(json.dumps(result,indent=2,default=str))
if __name__=="__main__":main()
