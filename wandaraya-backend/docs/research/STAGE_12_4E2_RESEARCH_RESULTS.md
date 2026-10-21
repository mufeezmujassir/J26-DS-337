# Stage 12.4E.2 Human Evaluation and Statistical Validation

Status: **HUMAN_EVALUATION_COMPLETED_VERIFIED**

Two independent reviewers completed 1,650 genuine judgments. Mapping agreement was 79.05% (Cohen's kappa 0.6653). Seasonality agreement was 84.31% (Cohen's kappa 0.8095; ordinal weighted kappa 0.9544). All 135 disagreements were independently adjudicated.

The verified `stage12_4e2_ground_truth_v1` contains 720 month records across 60 queries. Ninety-six records are explicitly insufficient evidence; 52 queries have all 12 numeric relevance grades and are eligible for full ranking metrics.

For the activity-aware model, mean NDCG@5 is 0.8971, NDCG@12 is 0.9511, tie-aware Spearman is 0.7844, and Kendall tau-b is 0.6876 across 52 queries.

The district multivariable baseline has mean NDCG@5 0.9157. The paired activity-aware minus baseline difference is -0.0187, with exploratory 13-cluster bootstrap 95% interval [-0.0473, 0.0036]. Because the interval crosses zero, superiority is not established.
