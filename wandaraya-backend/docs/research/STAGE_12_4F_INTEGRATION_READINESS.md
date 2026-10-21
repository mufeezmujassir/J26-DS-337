# Stage 12.4F Diagnostics and Model Refinement

Stage 12.4F is completed with limitations. The 52 queries are an inspected benchmark. Fixed candidates are exploratory; the calibrated blend uses grouped cross-validation with every attraction-activity query and its 12 months kept together. Thirteen climate-source clusters are too few for strong selection claims. District multivariable remains the best-supported reference; no refined candidate is approved for production.
{
  "status": "INTEGRATION_READY_EXPERIMENTAL_NOT_ACTIVATED",
  "service": "ExperimentalSeasonalityScoringService",
  "contract_fields": [
    "score",
    "category",
    "model version",
    "climate provenance",
    "mapping confidence",
    "geographic evidence",
    "district proxy flag",
    "missingness",
    "explanation",
    "limitations"
  ],
  "composition": "Attach as an independent evidence dimension after semantic candidate retrieval; preserve time and holiday/event dimensions; combine only in an explicitly approved future reranker.",
  "production_ranking_changed": false
}
