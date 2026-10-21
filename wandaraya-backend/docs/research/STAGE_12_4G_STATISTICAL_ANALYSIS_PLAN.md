# Stage 12.4G Statistical Analysis Plan

The evaluator validates the frozen protocol and model hashes, prohibits Stage 12.4E.2 query overlap, requires exactly two finalized reviewers per item, rejects duplicates, requires adjudication of every disagreement, and retains `INSUFFICIENT_EVIDENCE` as missing. Only complete 12-month queries enter NDCG@3/5/12, tie-aware Spearman, Kendall tau-b, top-3 overlap, and MRR analyses.

The primary estimate is paired query-level activity-aware minus district-reference NDCG@5. Uncertainty resamples climate-source identities rather than treating dependent attraction queries as independent. Geographic and activity subgroup results are secondary. No prospective metric is emitted before the provenance and completeness gates pass.

Current output is `PROSPECTIVE_VALIDATION_PENDING`, with no NDCG, significance, or model approval reported.

