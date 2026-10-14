# Stage 10.0.2 — Semantic Candidate–Weather Context Integration

**Status:** COMPLETE_WITH_LIMITATIONS  
**Date:** 2026-10-13  
**Scope:** Read-only integration of existing semantic retrieval and weather
suitability components. No ingestion, embedding, database migration, forecast
training, model approval, Airflow schedule, or scoring-rule change was made.

## Objective

Attach independent activity-specific weather evidence to semantic attraction
candidates while preserving the original Qdrant relevance score and ordering.
This stage does **not** apply a final recommendation ranking or claim that
weather enrichment improves ranking quality.

## Verified compatibility

- `SemanticAttractionRetriever.search(db, query, limit)` returns active
  PostgreSQL attractions after Qdrant retrieval, carrying canonical attraction
  ID and Qdrant similarity score.
- Attraction latitude/longitude are nullable scalar fields; they are not an
  attraction PostGIS geometry. District IDs are nullable.
- Activities and categories are association-table relationships. Activity names
  are mapped through `map_activity_to_weather_profile`; unsupported names remain
  visible rather than being guessed.
- `AttractionWeatherSuitabilityService.evaluate_batch` has request-local weather
  context caching by district/coordinate tuple. The integration calls it once
  for all eligible semantic candidates.
- The calibrated 0–100 batch score is converted only via the established
  `WeatherDimensionAdapter`. The resulting 0–1 value is a calibrated weather
  context dimension, not semantic relevance and not a final rank.

## Architecture

```text
Natural-language query + Sri Lanka travel date
  -> existing SemanticAttractionRetriever (Qdrant + active PostgreSQL records)
  -> canonical candidate envelope and ID deduplication
  -> batched metadata hydration (activities, categories, source provenance)
  -> existing activity mapper
  -> existing AttractionWeatherSuitabilityService + WeatherContextService
  -> existing calibration + WeatherDimensionAdapter
  -> independent semantic and weather evidence response
```

Duplicate canonical attraction IDs use the first occurrence returned by Qdrant:
that is the existing highest semantic rank. Equal-score ties retain Qdrant's
returned order. No semantic score is modified.

## API

`POST /api/v1/recommendations/context-enrich`

```json
{
  "query": "Peaceful nature attractions with scenic views",
  "travel_date": "2026-10-18",
  "top_k": 10,
  "forecast_mode": "production"
}
```

`forecast_mode` accepts `production` or `planning`. Production preserves the
existing approval-aware source policy. Planning uses the established historical
monthly-climatology behaviour where applicable; it is explicitly not a
day-specific forecast.

Every response has `ranking_applied: false`. Each candidate contains:

- untouched semantic score/rank/source;
- canonical attraction ID, stored metadata, category/activity names and source
  description provenance;
- exact-attraction or explicitly marked `district_fallback` coordinates;
- raw 0–100 attraction weather score, when available;
- existing calibrated 0–1 weather dimension, eligibility and limitations;
- source, resolution, reliability/calibration metadata, activity factors and
  explicit unknown state.

No score is fabricated. Missing district, unsupported/no activity mapping, or
unavailable weather yields `weather.status = "unknown"` and null scores.

## Scientific and operational safeguards

- Only existing approval-aware weather selection is used; no candidate artifact
  is approved or treated as a production model.
- The monthly-rainfall safety behaviour remains in the existing weather scorer;
  monthly totals are not treated as daily rain or precipitation probability.
- District-centroid fallback is marked in provenance and never represented as an
  attraction-exact observation.
- The service performs read queries only and makes no writes to attraction,
  weather, Qdrant, registry, artifact, or Airflow state.
- Marine activities retain their existing additional-condition limitations.

## Tests executed

Executed inside `wandaraya-api`:

```cmd
docker exec -i wandaraya-api python -m pytest tests/test_knowledge_base_api.py tests/weather_model/test_weather_context_service.py tests/weather_model/test_attraction_suitability.py tests/recommendation/test_weather_adapter.py tests/recommendation/test_semantic_weather_context_enrichment.py -q
```

Result: **22 passed, 0 failed, 0 skipped** (one third-party deprecation
warning). The focused Stage 10.0.2 plus adjacent adapter/suitability command
also passed **14 tests**.

The tests use mocked semantic/provider dependencies and do not call Google
Places, OpenWeather, Qdrant, or Wikipedia/Wikivoyage. FastAPI route registration
was separately checked by importing `app.main`; the endpoint is registered.

## Limitations and Stage 10.1 readiness

Live semantic retrieval still requires operational BGE and Qdrant services.
Short-term live weather still depends on a configured provider and valid
coordinates. With zero production-approved monthly models, production requests
outside the live-provider horizon correctly return unknown rather than a model
forecast. This stage intentionally has no time-of-day, Poya/holiday,
seasonality, group-emotion, final re-ranking, or recommendation explanation.

Stage 10.1 can begin **only as a separate, explicitly scoped context-layer
stage**. Its design must consume this independent contract and must not treat
the `dimension.score` as a final recommendation score.
