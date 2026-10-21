# Stage 12.4G Prospective Validation Protocol

Status: **FROZEN BEFORE PROSPECTIVE LABELS**

The version is `stage12_4g_prospective_protocol_v1`; the canonical SHA-256 is stored in `data/evaluation/stage12_4g/prospective_protocol_manifest.json`. The primary question compares the frozen original activity-aware model (`12.4d_v1`) with the frozen district multivariable reference (`12.4c_v1`) on genuinely new attraction–activity queries. The primary metric is mean NDCG@5 over complete 12-month queries. The retrospectively inspected fixed blend is not a primary candidate.

The feasibility target is 72 queries. Full-ranking analysis requires at least 60 complete queries and 15 climate-source clusters. This does not assert guaranteed statistical power. The primary paired difference uses a two-sided 95% climate-source-cluster bootstrap with seed 12404 and 10,000 iterations. `SUPPORTED_IMPROVEMENT` requires a mean NDCG@5 gain of at least 0.01 and a lower confidence bound above zero. Otherwise sufficient data yields `NO_ESTABLISHED_IMPROVEMENT`; insufficient query/cluster/adjudication coverage yields `INSUFFICIENT_INDEPENDENT_EVIDENCE`.

Month is the deterministic tie-break for predicted ranks; Spearman uses average tied ranks and Kendall uses tau-b. Insufficient evidence is missing, never grade zero. Incomplete 12-month queries are excluded from full-ranking metrics. Secondary analyses are Holm-adjusted if inferential p-values are used; otherwise they remain descriptive and exploratory.

