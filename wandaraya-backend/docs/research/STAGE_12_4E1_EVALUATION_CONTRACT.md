# Stage 12.4E.1 Evaluation Contract

The primary unit is one attraction–activity query with the 12 calendar months as candidates. A method ranks those months; independent month-level judgments are the only ground truth. Ranking attractions for a tourist query is outside this task. Mapping validity is a separate classification task. Model agreement and ablation analyses are exploratory behavior, not accuracy.

Unjudged months are not treated as irrelevant. NDCG is reported only at cutoffs with adequate independent judgments. `INSUFFICIENT_EVIDENCE` is excluded with missingness reported. Model predictions and reviewer submissions are stored separately.
