# Stage 10.0.1 — Knowledge Base–Weather Integration Audit

**Audit date:** 2026-10-13  
**Status:** READY_WITH_GAPS  
**Scope:** Read-only repository audit. No ingestion, retraining, migrations, model approval, Airflow trigger, or data-store mutation was performed.

## 1. Executive summary

The repository contains two compatible, but currently separate, Component 1 capabilities:

1. A Tourism Knowledge Base (KB) that discovers, stores, enriches, embeds, and retrieves Sri Lankan attractions.
2. A Weather Context Layer that selects safe weather evidence and calculates attraction/activity weather suitability.

There is already a direct district-level bridge: `GET /api/v1/weather/attractions` loads active KB attractions, maps their activities to weather profiles, caches context by district/coordinate pair during the request, and returns calibrated per-attraction weather results. There is also a future re-ranker contract, `WeatherContextDimension`, but no public recommendation or semantic-plus-weather re-ranking endpoint is registered.

The main Stage 10.0.2 work is therefore not creating a weather scorer. It is defining a candidate envelope that preserves semantic relevance, candidate provenance, and visit context while invoking the existing batch weather service exactly once per appropriate location/date group.

Previously reported Weather Layer values (not re-verified by this audit) are 204 tests, 58 valid candidate artifact checksums, 43 registered series, and zero production-approved models.

## 2. Verified repository structure

| Area | Actual paths | Notes |
|---|---|---|
| FastAPI entry point | `app/main.py:26-29` | Creates `app`; router registration at lines 39 and 147-153. |
| KB API | `app/routers/knowledge_base.py:37-242` | Read-only Swagger API under `/api/v1/knowledge-base`. |
| KB discovery/ingestion | `app/knowledge_base/discovery/`, `app/knowledge_base/pipelines/attraction_ingestion_pipeline.py` | Discovery and ingestion exist separately from public reads. |
| KB processing | `app/knowledge_base/processors/` | Validator, normalizer, deduplicator, district resolver, category/activity mapper. |
| KB enrichment | `app/knowledge_base/enrichment/wikipedia_enricher.py`, `wikivoyage_enricher.py` | Sourced description enrichment. |
| Embeddings/retrieval | `app/knowledge_base/embeddings/`, `app/knowledge_base/retrieval/semantic_retriever.py` | BGE model and Qdrant retrieval. |
| Attraction persistence | `app/models/attraction.py`, `district.py`, `attraction_activities.py`, `attraction_categories.py`, `attraction_descriptions.py` | SQLAlchemy ORM; district boundary is a PostGIS multipolygon. |
| Weather context | `app/weather_model/context/` | Source routing, live provider, monthly provider, climatology provider and unified context service. |
| Forecast reliability | `app/weather_model/forecasting/forecast_service.py`, `reliability.py`, `fallback_policy.py` | Artifact approval/checksum/evidence verification. |
| Weather scoring | `app/weather_model/context_scoring/`, `app/weather_model/suitability/` | Independent 0–1 context score plus 0–100 calibrated attraction score. |
| Re-ranker interface | `app/recommendation/context_dimensions/weather_context_contract.py`, `weather_adapter.py` | Contract/adapter exists; no full re-ranker router is registered. |
| Orchestration | `dags/weather_live.py`, `weather_historical.py`, `weather_model_train.py`, `weather_predictions_cache.py` | Four weather DAGs; not triggered by this audit. |

## 3. Knowledge Base architecture and data flow

```text
Configured sources (Google Places, Wikipedia, Wikivoyage)
  -> discovery / ingestion pipeline
  -> validator + normalizer + deduplicator + district resolver
  -> attractions, districts, categories, activities and descriptions in PostgreSQL
  -> attraction document builder + BGE embedding
  -> Qdrant collection sri_lanka_attractions
  -> SemanticAttractionRetriever Top-K search
  -> PostgreSQL active-attraction hydration
  -> read-only KB API response
```

### 3.1 Data model findings

| Finding | Verified implementation |
|---|---|
| Attraction primary key | `Attraction.id`, auto-increment integer: `app/models/attraction.py:9`. |
| External identifier | Unique nullable `google_place_id`: `app/models/attraction.py:19`; unique `slug` at line 11. |
| District representation | Nullable attraction foreign key `district_id`: line 14; `District.id`, name/province and `MULTIPOLYGON` SRID 4326 boundary in `app/models/district.py:9-15`. |
| Attraction coordinates | Nullable numeric `latitude` / `longitude`, `app/models/attraction.py:16-17`; separate JSON `location` at line 18. They are not an attraction PostGIS point column. |
| Categories | Many-to-many association with uniqueness on `(attraction_id, category_id)`: `app/models/attraction_categories.py:6-8`. |
| Activities | Many-to-many association with uniqueness on `(attraction_id, activity_id)`: `app/models/attraction_activities.py:6-16`. It also stores duration, age, difficulty and availability. |
| Activity vocabulary | Stored as `Activity.name`; it is normalized to weather profiles through aliases at the weather boundary (`app/weather_model/suitability/activity_mapper.py`). It is not guaranteed that every stored name is already a weather profile key. |
| Provenance | `AttractionDescription` stores source ID, title, URL, language, content hash, retrieved timestamp and active state: `app/models/attraction_descriptions.py:7-20`; public detail API joins `DataSource` at `app/routers/knowledge_base.py:152-164`. |
| Opening hours | Present in `Attraction.opening_hours` JSON: `app/models/attraction.py:25`, but absent from `KnowledgeBaseAttractionDetail` response schema (`app/schemas/knowledge_base.py:59-66`). |
| Visit duration | Present per relationship as nullable `AttractionActivity.duration_minutes`: `app/models/attraction_activities.py:14`, but not exposed by KB summary/detail response schemas. |

### 3.2 Retrieval interfaces

`SemanticAttractionRetriever.search(db, query, limit=10)` is the candidate retrieval entry point at `app/knowledge_base/retrieval/semantic_retriever.py:48-53`.

- It embeds the query with `AttractionEmbeddingService.encode_query` at lines 56-62.
- It asks Qdrant for `limit` points at lines 65-71, therefore Top-K is supported.
- It retains Qdrant similarity score and attraction ID at lines 83-103.
- It hydrates active PostgreSQL `Attraction` records at lines 114-126.
- It returns `SemanticCandidate(attraction_id, name, score, city, district_id)` at lines 140-147.
- The public API performs an additional summary hydration and returns `semantic_score`: `app/routers/knowledge_base.py:237-255` and `app/schemas/knowledge_base.py:69-70`.

The configured/default embedding model is `BAAI/bge-large-en-v1.5` in `app/knowledge_base/embeddings/embedding_service.py:16-21`. Qdrant uses collection `sri_lanka_attractions`, 1024 dimensions and cosine distance in `app/knowledge_base/embeddings/qdrant_indexer.py:18-40`.

Candidate enrichment already exists: the ingestion pipeline and Wikipedia/Wikivoyage enrichers produce `AttractionDescription` records. The audit found no separate runtime candidate-enrichment stage after semantic retrieval.

## 4. Weather Context interfaces

### 4.1 Forecast reliability

`ForecastService.get_forecast(...)` is defined at `app/weather_model/forecasting/forecast_service.py:29-96`.

Required inputs are `district_id`, `target`, `forecast_date`, `reference_date`; `latitude` and `longitude` are optional but must be supplied together (lines 32-42). Targets are rainfall, minimum temperature and maximum temperature. The result is `ReliableForecastResult` with status, value, unit, source, model version, production flag and reliability metadata (`app/weather_model/forecasting/schemas.py:22-31`).

The documented selector horizon is five days live, then up to 90 days monthly forecast, then climatology: `app/weather_model/context/source_selector.py:13-48`.

Artifact verification rejects absent registry entries, unapproved entries, checksum/version/evidence mismatch, district/target mismatch and model mismatch (`app/weather_model/forecasting/reliability.py:32-67`). `ForecastService` only returns an artifact forecast after that verification and after verifying the forecast date is after training cutoff (`forecast_service.py:76-96`).

### 4.2 Weather context and status handling

`WeatherContextService.get_context(district_id, travel_date, latitude, longitude, reference_date, planning_mode)` is at `app/weather_model/context/weather_context_service.py:41-49`.

- 0–5 days: live OpenWeather data requires coordinates; unavailable data returns an unavailable `UnifiedWeatherContext` (lines 88-150).
- 6–90 days: normal production mode uses the monthly provider and rejects every unapproved item (lines 152-228).
- Explicit planning mode switches that middle window to historical monthly climatology without bypassing production approval for candidate artifacts (lines 57-76).
- Long-range climatology returns an explicitly non-daily source with monthly historical rainfall period and `is_daily_forecast: false` provenance (lines 230-290).
- Unified availability, source, resolution, values, missing targets, provenance and message are defined in `app/weather_model/context/schemas.py:131-157`.

### 4.3 Weather suitability and contract

There are two compatible weather scoring surfaces:

1. `WeatherSuitabilityEngine.score(AttractionWeatherRequest)` — explainable 0–1 context score at `app/weather_model/context_scoring/weather_suitability.py:16-76`.
2. `AttractionWeatherSuitabilityService.evaluate_batch(...)` — calibrated per-attraction API scoring at `app/weather_model/suitability/attraction_service.py:22-60`.

`WeatherSuitabilityEngine` returns `unknown` with a null score if weather is unavailable or reliability is unavailable (lines 29-38). It only uses daily/interval rain values as a rain penalty; a monthly total is explicitly informational and not read as daily rainfall or rain probability (lines 55-67).

The six context-scoring rules are hiking, beach, wildlife safari, heritage site, water activities and indoor attraction in `app/weather_model/context_scoring/activity_weather_rules.py:17-35`. The attraction suitability layer supports a broader internal profile vocabulary and reports unsupported activity types instead of silently scoring them (`app/weather_model/suitability/attraction_service.py:108-124`).

`WeatherContextDimension` is the present re-ranker contract (`app/recommendation/context_dimensions/weather_context_contract.py:17-46`). It preserves attraction ID, availability, eligibility, 0–1 score, source, resolution, reliability, explanations and factors. It does not perform ranking.

## 5. Field compatibility matrix

| KB/retrieval field | Weather input/output | Compatible? | Required transformation | Source |
|---|---|---:|---|---|
| `Attraction.id` / `SemanticCandidate.attraction_id` | `AttractionWeatherCandidate.attraction_id`; `WeatherContextDimension.attraction_id` | Yes | Direct integer pass-through. | `app/models/attraction.py:9`; `semantic_retriever.py:15-20`; `weather_context_contract.py:17-18` |
| `district_id` | Weather context and all suitability calls require positive `district_id` | Conditional | Reject/make unknown when null; do not infer a different district. | `attraction.py:14`; `weather_context_service.py:41-49` |
| `latitude`, `longitude` | Live context location | Conditional | Pass as a pair. For short-term live forecast, missing pair yields unavailable. | `attraction.py:16-17`; `weather_context_service.py:88-100` |
| District centroid | Fallback location in KB weather repository | Conditional | Only used when attraction coordinates missing; preserve `coordinate_source=district_fallback`. | `app/weather_model/suitability/attraction_repository.py:106-121` |
| `activities: list[str]` | Weather profile key(s) | Conditional | Map with `map_activity_to_weather_profile`; retain unsupported names for explicit reporting. | `app/routers/knowledge_base.py:40-56`; `activity_mapper.py` |
| Multiple activity relationships | `activity_types: list[str]` | Yes | Preserve relationships; same profile keys can repeat to keep coverage metrics truthful. | `attraction_repository.py:91-101`; `attraction_service.py:112-166` |
| Qdrant `score` | Candidate relevance score | Not yet in weather request/result | Stage 10.0.2 must carry it in a candidate envelope and preserve it separately from weather score. | `semantic_retriever.py:98-102`; `schemas/knowledge_base.py:69-70` |
| `travel_date` | `date` | Yes | Caller supplies one date per batch; no visit-time field exists. | Weather route signatures / context service lines 41-49 |
| Time zone | No explicit KB field | Gap | Define Sri Lanka-local visit-date/time convention in integration request schema. Live provider already aggregates a Sri Lanka-local calendar day by contract. | `context/schemas.py:76-99` |
| Opening hours | No current weather input | Stored, not API exposed | Stage 10.0.2 may expose it for later time-of-day filtering; weather layer does not use it. | `attraction.py:25`; `knowledge_base.py:59-66` |
| `duration_minutes` | No current weather input | Stored, not candidate API exposed | Preserve for future itinerary/time-of-day layer; do not invent duration. | `attraction_activities.py:14` |
| Source provenance | Weather provenance | Separate but compatible | Return both independently; do not replace KB provenance with weather provenance. | `attraction_descriptions.py:11-19`; `weather_context_contract.py:24-28` |

## 6. API inventory

| Method | Route | Handler | Request | Response |
|---|---|---|---|---|
| GET | `/health` | `health_check` | none | service-status dictionary |
| POST | `/internal/knowledge-base/refresh` | `refresh_knowledge_base` | `X-Airflow-Token` | refresh result dictionary; protected/mutating |
| POST | `/internal/knowledge-base/discovery` | `discover_knowledge_base` | `DiscoveryRequest`, `X-Airflow-Token` | discovery/ingestion dictionary; protected/mutating |
| GET | `/api/v1/knowledge-base/status` | `knowledge_base_status` | none | `KnowledgeBaseStatus` |
| GET | `/api/v1/knowledge-base/attractions` | `list_attractions` | district/category/activity/limit query values | `list[KnowledgeBaseAttractionSummary]` |
| GET | `/api/v1/knowledge-base/attractions/nearby` | `nearby_attractions` | lat/lon/radius/limit | `list[NearbyAttraction]` |
| GET | `/api/v1/knowledge-base/attractions/{attraction_id}` | `get_attraction` | path ID | `KnowledgeBaseAttractionDetail` |
| GET | `/api/v1/knowledge-base/categories` | `list_categories` | none | `list[KnowledgeBaseCategory]` |
| GET | `/api/v1/knowledge-base/districts` | `list_districts` | none | `list[KnowledgeBaseDistrict]` |
| GET | `/api/v1/knowledge-base/sources` | `list_sources` | none | `list[KnowledgeBaseSourceCoverage]` |
| GET | `/api/v1/knowledge-base/quality` | `quality_report` | none | `KnowledgeBaseQualityReport` |
| GET | `/api/v1/knowledge-base/semantic-search` | `semantic_search` | query, limit | `list[SemanticSearchResult]` |
| GET | `/api/v1/weather/forecasts/{district_id}` | `get_district_forecasts` | path ID, `include_unapproved` | dictionary of persisted runs/forecasts |
| GET | `/api/v1/weather/forecasts/{district_id}/status` | `get_district_forecast_status` | path ID | dictionary of run freshness/status |
| GET | `/api/v1/weather/context/{district_id}` | `get_weather_context` | date, coordinates, forecast mode | `UnifiedWeatherContext` |
| GET | `/api/v1/weather/suitability/{district_id}` | `get_weather_suitability` | date, activity, coordinates, forecast mode | `IntegratedSuitabilityResponse` |
| GET | `/api/v1/weather/attractions` | `get_attraction_weather` | district/date/limit/forecast mode | `AttractionWeatherBatchResponse` |
| POST | `/api/v1/weather/suitability/batch` | `evaluate_attraction_weather_batch` | `AttractionWeatherBatchRequest` | `AttractionWeatherBatchResponse` |
| POST | `/api/route/validate` | `validate_route` | `RouteValidationRequest` | `RouteResult` |

No public recommendation router is registered: `app/main.py:154-156` only contains a commented future recommendation-router example.

## 7. Tests and safe commands

| Command | Classification | Audit result |
|---|---|---|
| `docker exec -it wandaraya-api python -m pytest tests/test_knowledge_base_api.py -q` | Safe isolated test | Not run in this audit: Docker engine was unavailable (`pipe ... system cannot find the file specified`). |
| `docker exec -it wandaraya-api python -m pytest tests/weather_model/test_weather_context_service.py tests/weather_model/test_attraction_suitability.py -q` | Safe isolated test | Not run for the same Docker availability reason. |
| `python -m scripts.validate_weather_data` | Reads processed CSV; validation only | Safe only if its configured file paths are present; not executed. |
| `python -m scripts.generate_weather_coverage_report` | Reads CSV and writes a report | Not executed because this audit permits only the two required audit reports to change. |
| `python -m scripts.test_semantic_retrieval` | Uses BGE + Qdrant and database | Not run: may load model/use service resources. |
| `python -m scripts.test_qdrant_indexing` | Qdrant upsert | Not safe: writes vector data. |
| `python -m scripts.test_attraction_discovery` | External Google Places calls; optional ingestion | Not run; requires credential/provider use. |
| `python -m scripts.test_attraction_ingestion_pipeline` | External calls, PostgreSQL and Qdrant writes | Not safe. |
| Wikipedia/Wikivoyage test scripts | External requests and database commits | Not safe. |
| `scripts/run_final_weather_forecasts.py` | Trains/persists forecasts/reports | Not safe. |
| `scripts/review_weather_model_approval.py` | Changes approval status | Not safe. |

Relevant existing test modules include `tests/test_knowledge_base_api.py`, `tests/weather_model/test_weather_context_service.py`, `test_attraction_suitability.py`, `test_forecast_reliability_service.py`, `test_context_scoring.py`, `test_airflow_weather_orchestration.py`, and `tests/recommendation/test_weather_adapter.py`.

## 8. Integration gaps and risks

1. **No candidate envelope:** semantic candidates contain relevance score, but attraction-weather request/result schemas do not preserve it.
2. **No public re-ranker/recommendation endpoint:** the registered API ends at independent weather output and a route-validation endpoint.
3. **No explicit visit timezone/time:** dates are compatible, but visit time/timezone policy is not defined in the KB-to-weather contract.
4. **Opening hours and duration are stored but not exposed in current KB candidate responses.**
5. **Missing district/coordinates need explicit integration behavior:** the current weather repository can use district centroid as a marked fallback; semantic candidates require a similar documented policy.
6. **Activity vocabulary is only partially canonical at storage level:** aliases exist, but unsupported values must remain visible rather than be guessed.
7. **Duplicate handling needs an integration boundary:** Qdrant points identify an attraction, but a combined candidate list needs explicit attraction-ID deduplication while retaining the best semantic score/provenance.
8. **Caching is request-local only:** `AttractionWeatherSuitabilityService` caches context by district and coordinate pair during one batch (`attraction_service.py:32-50`). There is no documented cross-request cache for a semantic-plus-weather integration.
9. **Production long-range availability is intentionally limited:** with no approved model, default 6–90 day production requests return unavailable. Planning mode is historical monthly guidance, not a daily forecast.

## 9. Recommended Stage 10.0.2 architecture

Create a read-only orchestration service, not a duplicate weather engine:

```text
SemanticAttractionRetriever Top-K
  -> hydrate canonical KB candidate envelope
  -> deduplicate by attraction_id while retaining max semantic score/source
  -> map activities through existing mapper
  -> call existing AttractionWeatherSuitabilityService in one batch
  -> transform each weather result through WeatherDimensionAdapter
  -> return candidate relevance + weather dimension side by side
```

The service must retain source provenance, semantic score, `coordinate_source`, weather availability, reliability, explanations and unknown status. It must not average semantic and weather scores until the re-ranker scoring policy is separately approved.

## 10. Exact Stage 10.0.2 task breakdown

1. Define Pydantic request schema: query, travel date, optional top-K, explicit forecast mode, Sri Lanka-local visit-time convention.
2. Define a canonical candidate envelope with attraction ID, semantic score, source/provenance, district, coordinates, activities, categories and explicit missing fields.
3. Build a read-only semantic-candidate-to-weather adapter using the existing retriever and `AttractionWeatherSuitabilityService`.
4. Deduplicate by attraction ID; preserve maximum semantic score and source provenance.
5. Reuse `map_activity_to_weather_profile`; report unsupported activities in the response.
6. Group/cache weather context by `(district_id, latitude, longitude, travel_date, forecast_mode)` without changing existing provider behavior.
7. Convert weather results with `WeatherDimensionAdapter`; preserve null/unknown weather instead of inventing scores.
8. Add a dedicated integration endpoint and tests for IDs, missing district/location, duplicate candidates, unsupported activities, no weather, live weather, planning mode and unapproved models.
9. Do not approve models, change coverage policy, train artifacts or write KB data.

## 11. Acceptance criteria for Stage 10.0.2

- A Top-K semantic candidate list can be evaluated for one travel date without losing candidate relevance scores.
- Every response preserves canonical attraction ID, district/location provenance, semantic relevance and a separate weather dimension.
- Missing or unsupported data is explicit; no district substitution or fabricated weather is made.
- Weather unavailable produces `score: null` / ineligible weather dimension, not an arbitrary penalty.
- Monthly planning outputs remain labelled as seasonal estimates and never interpret monthly rainfall as daily weather.
- No candidate model is used as a production model without explicit prior approval.
- Tests cover duplicate IDs, null district, null coordinates, activity aliases, unsupported activity, provider unavailability and planning mode.

## 12. Known limitations and unresolved questions

- Which later component owns the final combined relevance-plus-weather ranking formula is not implemented here.
- Opening-hours and visit-duration exposure needs a separate API/schema decision before time-of-day planning.
- The exact cache storage/TTL for the combined integration is not implemented.
- The audit did not run Docker-based tests because the Docker engine was unavailable at the time of the safe validation attempt.
- The current KB weather endpoint evaluates active district attractions with activity mappings; it is not semantic Top-K retrieval followed by weather re-ranking.
