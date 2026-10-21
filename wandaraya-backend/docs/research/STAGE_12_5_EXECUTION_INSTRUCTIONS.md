# Stage 12.5 Execution Instructions

All flags default to false. For an isolated research deployment, set `ENABLE_UNIFIED_CONTEXT_ENGINE=true`, `ENABLE_UNIFIED_CONTEXT_EXPERIMENTAL_RERANKING=true`, and `ENABLE_UNIFIED_CONTEXT_RESEARCH_API=true`; configure a research token of at least 32 characters. Keep `ENABLE_UNIFIED_CONTEXT_PRODUCTION_RANKING=false`.

Call `POST /api/v1/research/recommendations/context-aware` with `X-Research-Token`. `travel_datetime` must include a timezone. Supply `requested_activities` for weather suitability and `activity_type_id` for seasonality.

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/recommendation/test_unified_context_*.py -q
```

Run diagnostic evaluation:

```powershell
.\.venv\Scripts\python.exe scripts/run_stage12_5_unified_evaluation.py --query "morning beach visit" --travel-datetime "2027-01-15T08:00:00+05:30" --activity "beach"
```

Run the shadow pilot only against configured real services:

```powershell
.\.venv\Scripts\python.exe scripts/run_stage12_5_shadow_pilot.py --input data/stage12_5_shadow_scenarios.json
```
