# Stage 12.4E Evaluation Protocol (Prepared, Not Executed)

The test dataset is frozen before tuning. Historical climate inputs, rule mappings, computed scores, and independent judgments remain separate. No computed score is a human relevance label.

For ranking the 12 calendar months of an attraction–activity pair, report NDCG@3, NDCG@5 only where five judged relevant positions are meaningful, Spearman correlation, Kendall tau, top-3 overlap, and MRR only under a preregistered binary relevance definition. Attraction ranking is a different task and requires a separate query–attraction judgment dataset.

Compare rainfall-only, district multivariable, rainfall risk-adjusted, activity-aware, and the activity-aware Cohort A subset. Baseline E is a subset, not another algorithm. Planned ablations remove temperature, humidity, reliability, geographic specificity, and activity-specific profiles one at a time without retuning the frozen test set.

Use paired bootstrap confidence intervals and cluster-aware resampling by district or climate-source identity because many attractions share proxies. Keep duplicate and near-duplicate attractions in the same split. Recommended development splitting groups by district/climate source; freeze a held-out district-group test set before calibration. Do not run significance tests until genuine independent labels exist. Mapping recall is reportable only if the sampling frame supports population estimation; use inverse-probability weighting for the stratified sample where justified.
