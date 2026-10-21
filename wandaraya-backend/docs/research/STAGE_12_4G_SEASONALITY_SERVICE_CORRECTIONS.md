# Stage 12.4G Seasonality Service Corrections

`ExperimentalSeasonalityScoringService` remains read-only and experimental. It now supports batched mapping/profile/baseline queries and returns the explicit states `FALLBACK_NOT_REQUIRED`, `DISTRICT_BASELINE_FALLBACK_APPLIED`, `FALLBACK_UNAVAILABLE`, `PROFILE_UNAVAILABLE`, and `MAPPING_UNSUPPORTED`.

A fallback is marked used only when the district multivariable score is actually returned. If a weak mapping has no matching district baseline, the weak stored profile is not silently trusted and the score is unavailable. Missing mappings and profiles use an explicit unavailable result contract. The request geographic field is retained for compatibility but cannot override persisted `climate_source_type`; mismatches are recorded.

Every result identifies `HISTORICAL_CLIMATE_SEASONALITY`, states that it is not `LIVE_WEATHER_FORECAST`, preserves model/category/reference/source/mapping/missingness/explanation fields, and asserts `production_ranking_changed=false`.

