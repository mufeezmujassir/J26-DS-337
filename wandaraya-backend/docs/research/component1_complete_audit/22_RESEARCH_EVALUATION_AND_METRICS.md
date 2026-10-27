# Research Evaluation and Metrics

| Metric | Definition/use |
|---|---|
| Precision@K | relevant retrieved / K; needs relevance labels |
| Recall@K | relevant retrieved / all relevant; needs complete-enough ground truth |
| DCG@K | `Σ(2^rel_i-1)/log2(i+1)`; rewards early relevance |
| NDCG@K | DCG divided by ideal DCG; comparable across queries |
| MRR | mean reciprocal rank of first relevant result |
| MAP | mean average precision across queries |
| Spearman | rank correlation based on rank differences |
| Kendall tau | concordant minus discordant pair proportion |
| Top-K overlap | set overlap; stability, not relevance |
| evidence coverage | candidates with eligible evidence / candidates |
| latency | response-time distribution, report median and tails |
| error rate | failed requests / attempted requests |
| Cohen/weighted kappa | chance-corrected reviewer agreement |
| confidence interval | uncertainty around an estimated metric |
| SUS | 10-item usability questionnaire; needs actual users |

An ablation holds queries/judgments fixed and compares R0, R1, R2 and R3; report per-query effects, confidence intervals and evidence coverage. Accuracy must use independent human relevance/context judgments, not tests or model agreement.

Measured artifact evidence: Stage 12.4F exploratory NDCG@5 values of approximately .8971 activity-aware, .9157 district baseline and .9161 retrospective blend over 52 valid queries (C). Stage 12.4G prospective protocol has 72 queries/864 items/23 clusters but zero human judgments. Stage 12.6 observed 3/3 requests completed and 15 candidates, an execution sample only. Recommendation accuracy is therefore **not validated**.

Example: relevance `[3,2,0]` gives `DCG@3=(7/log2(2))+(3/log2(3))+(0/log2(4))`; NDCG divides this by the best possible ordering. Never compare an NDCG produced from different judgment pools as if identical.

