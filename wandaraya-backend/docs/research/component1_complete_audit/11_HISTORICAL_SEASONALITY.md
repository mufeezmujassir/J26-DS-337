# Historical Seasonality

Historical seasonality is an explainable statistical/rule-based context layer, not a neural model. NASA POWER daily observations are aggregated into district/month climatology and mapped to attraction/activity profiles. At audit runtime there were 165,828 daily observations, 10,127 attraction/activity mappings and 121,524 seasonality profile rows (B).

Baseline B is `0.45*rainfall_favorability + 0.25*temperature_comfort + 0.15*humidity_comfort + 0.15*solar_normalization` (`app/climate/services/seasonality_features.py:74-98`). Temperature comfort is a Gaussian centered at 25°C with sigma 5°C; humidity is penalized above 65%; rainfall reliability is `1-clamped(CV)`. Data is based on a 0.5° grid and does not claim attraction-level microclimate.

The read service requires a valid mapping/profile. Strong mapping returns mapped evidence; weaker mappings may use district-reference evidence when explicitly supported; missing mapping/profile returns unavailable. This abstention is why seasonality can be absent for a candidate.

Existing Stage 12.4F exploratory artifact: 52 valid queries, activity-aware NDCG@5 0.8971, district multivariable 0.9157 and a retrospective fixed blend 0.9161 (C). Baseline B was conservatively selected because it was simpler and had prior human-benchmark evidence. These results are not prospective validation. Stage 12.4G froze 72 queries, 864 items and 23 clusters, but human judgments remain zero and validation pending.

Changing weights changes the climate preference; changing comfort centers/thresholds changes who/what “comfortable” means and requires re-evaluation. Changing mappings can alter evidence eligibility. No parameter should be tuned on final judgments without a documented train/validation protocol.

