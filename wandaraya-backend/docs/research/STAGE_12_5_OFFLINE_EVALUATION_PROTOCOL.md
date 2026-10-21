# Stage 12.5 Offline Evaluation Protocol

Run `scripts/run_stage12_5_unified_evaluation.py` with a real query, timezone-aware travel timestamp, and optional activity identifiers. It records R0–R3 outputs and creates a blinded review item.

No independent unified recommendation labels currently exist. Therefore the status is `UNIFIED_RANKING_ACCURACY_NOT_YET_VALIDATED`, and NDCG, Precision@5, MRR, or accuracy must not be reported. Stage 12.4E.2 month-ranking labels are not attraction-recommendation labels and are not reused. Future relevance judgments must be independent and separated from tuning data.
