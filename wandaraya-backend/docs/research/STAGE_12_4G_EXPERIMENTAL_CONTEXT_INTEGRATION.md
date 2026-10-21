# Stage 12.4G Experimental Context Integration

The internal composition flow is:

`SemanticAttractionRetriever.search` → batched metadata/evidence collection → `ExperimentalContextCompositionResponse`.

Candidate IDs and Qdrant order are preserved. Time evidence reuses the verified opening-hours parser/evaluator through `evaluate_attraction_time_evidence`. Holiday/Poya/Event evidence reuses `HolidayEventContextScoringService.score`. Historical seasonality uses `ExperimentalSeasonalityScoringService.score_batch`. No compatible Group Emotion context service exists, so that dimension is explicitly `NOT_AVAILABLE` with a null score.

Missing dimensions remain null rather than becoming zero, and no cross-dimension weights are introduced. No public route was added. `ENABLE_EXPERIMENTAL_CONTEXT_COMPOSITION`, `ENABLE_EXPERIMENTAL_SEASONALITY_EVIDENCE`, and `ENABLE_SEASONALITY_PRODUCTION_RERANKING` all default to false. The reranking flag is also guarded by the compositor and remains false.

