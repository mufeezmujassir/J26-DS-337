# WANDARAYA Component 1 — supervisor demonstration guide

## Confirmed scope on 12 October 2026

Component 1 is a Sri Lanka tourism Knowledge Base plus a completed, independent
Weather Context Layer. It is **not yet** the final five-dimension Context
Re-Ranker. Time-of-Day, Poya/Holiday, seasonality and group-emotion dimensions
remain outside the completed scope.

### Confirmed current outputs

| Item | Confirmed value | Meaning |
| --- | ---: | --- |
| Active attractions | 27 | All 27 have coordinates and a district mapping. |
| Categories configured | 18 | Taxonomy exists; some categories have no attraction mappings yet. |
| Activities configured | 50 | Activity mapping supports suitability interpretation. |
| Enrichment records | 19 | 13 Wikipedia and 6 Wikivoyage descriptions, stored separately from `attractions.description`. |
| Qdrant vectors | 27 | The `sri_lanka_attractions` collection exists with 1024-dimensional vectors. |
| Weather districts with observations | 16 of 25 | Unsupported districts are deliberately not fabricated. |
| Monthly weather rows | 873 | January 2021 through October 2025. |
| Registered weather series | 43 | One district-target evidence record per supported series. |
| Candidate artifacts | 58 | All passed SHA-256 integrity validation. |
| Production-approved models | 0 | Long-range model forecasts remain unavailable by design. |
| Weather tests | 204 passed, 0 failed, 0 skipped | Controlled end-to-end and regression validation. |

## What the system does

```text
Google Places / Wikipedia / Wikivoyage
  -> validation, normalization, de-duplication and district resolution
  -> PostgreSQL + PostGIS attraction knowledge
  -> semantic document -> BGE-large-en-v1.5 embedding -> Qdrant

Historical district weather -> validation / aggregation
  -> Prophet + monthly climatology + seasonal naive backtesting
  -> model-selection evidence -> registry -> immutable candidates
  -> live forecast OR manually approved monthly artifact OR unavailable
  -> activity-specific 0–1 Weather Context score
  -> Weather Context contract for the future Context Re-Ranker
```

## Technology and design decisions

### Knowledge Base

- **PostgreSQL** stores normalized attractions, categories, activities,
  source/enrichment records and weather metadata.
- **PostGIS / GeoAlchemy** supports district boundaries and future spatial
  filtering. The current attraction model stores latitude/longitude and a
  location payload; do not claim a particular spatial SQL query unless it has
  been run against this schema.
- **Google Places** supplies stable place identifiers and location metadata.
- **Wikipedia and Wikivoyage** enrich records with cultural and travel-oriented
  descriptions. Multiple sources are needed because no one source contains
  every field needed for tourism recommendation.
- **BGE-large-en-v1.5** is the configured pretrained embedding model. It emits
  **1024-dimensional** normalized vectors; it has not been fine-tuned on a
  custom Sri Lankan dataset.
- **Qdrant** stores vectors for semantic candidate retrieval. PostgreSQL then
  hydrates returned IDs into structured attraction records.

### Weather Layer

- **Prophet** is a candidate model for trend plus annual/monthly seasonal
  structure in short monthly district series; it is not assumed to be best.
- **Monthly climatology** is the average of the same calendar month in the
  available training history. It tests whether a simple seasonal baseline is
  already sufficient.
- **Seasonal naive** uses the corresponding prior seasonal observation
  (`y[t-12]`). It is a transparent recurrence baseline.
- **Rolling-origin backtesting** uses 36 minimum training months, a 3-month
  horizon and a 3-month step. It prevents future observations leaking into
  training.
- **MAE** measures typical absolute error, **RMSE** penalizes large errors, and
  **bias** shows systematic over- or under-prediction.
- **SHA-256** detects altered candidate artifacts. Registry evidence
  fingerprints invalidate a decision if its model-selection evidence changes.
- **OpenWeather** is only for short-range, provider-supported forecasts inside
  the five-day horizon. It is not a replacement for a monthly local model.
- **Airflow** orchestrates safe workflows, retries and logs. It does not
  approve models or invent data.

## Why three forecasting models?

The research question is not “can Prophet forecast weather?” It is “does
Prophet improve on simple seasonal methods for this district and target?”

| Model | Rule | Reason for inclusion |
| --- | --- | --- |
| Prophet | Trend + learned seasonality | Candidate that may capture changing seasonal structure. |
| Monthly climatology | Historical mean for calendar month | Strong, interpretable seasonal baseline. |
| Seasonal naive | Same month in previous year | Minimal seasonal persistence benchmark. |

### Actual Galle (district 78) evidence

| Target | Best provisional candidate | MAE comparison | Explanation |
| --- | --- | --- | --- |
| Rainfall | Monthly climatology | 105.0962 mm vs Prophet 134.3123 mm | Prophet was 27.8% worse than climatology. |
| Maximum temperature | Prophet | 0.5292°C vs climatology 0.5760°C | Prophet improved MAE by 8.12%. |
| Minimum temperature | Monthly climatology, review required | 0.3756°C vs Prophet 0.3762°C | Difference is only 0.16%; the selected baseline also has a bias flag. |

Each Galle series has seven independent origins and 21 shared observed
predictions across horizons 1–3. These are **provisional candidates**, not
production approvals.

## Data-quality rules to explain

- Temperature may use documented, training-only missing-aware preparation only
  when coverage is at least **95%**.
- Rainfall is never interpolated; a missing rainfall observation rejects strict
  rainfall candidate training.
- Evaluation actuals are never imputed.
- A district never receives another district's weather as a silent fallback.
- A monthly rainfall total is never treated as a daily total or rain
  probability.
- An unavailable or untrusted forecast produces `unknown` suitability with a
  null score, never an invented low score.

## Weather suitability

The 0–1 `WeatherSuitabilityEngine` is separate from the older calibrated
0–100 tourism weather scorer. Do not present them as one score.

It has six activity profiles: hiking, beach, wildlife safari, heritage site,
water activities and indoor attraction. Daily/three-hourly provider rainfall,
temperature and precipitation probability can change the score. Indoor
attractions receive a smaller rainfall penalty than exposed activities. The
output includes factor-level explanations and is converted to the independent
`weather-context-v1` contract for a future re-ranker.

## Windows CMD demonstration commands

Run from the repository root. These are read-only except where stated.

### 1. Infrastructure

```cmd
docker compose ps
curl http://localhost:8000/health
```

Expected health response:

```json
{"status":"ok","db":"ok","redis":"ok","qdrant":"ok"}
```

### 2. Actual Knowledge Base counts

```cmd
docker exec wandaraya-postgres psql -U postgres -d wandaraya -P pager=off -c "SELECT COUNT(*) AS attractions, COUNT(*) FILTER (WHERE is_active) AS active, COUNT(*) FILTER (WHERE latitude IS NOT NULL AND longitude IS NOT NULL) AS with_coordinates, COUNT(*) FILTER (WHERE district_id IS NOT NULL) AS district_mapped FROM attractions; SELECT COUNT(*) AS categories FROM categories; SELECT COUNT(*) AS activities FROM activities; SELECT ds.name, COUNT(ad.id) AS enrichment_descriptions FROM data_sources ds LEFT JOIN attraction_descriptions ad ON ad.source_id=ds.id GROUP BY ds.id,ds.name ORDER BY enrichment_descriptions DESC,ds.name;"
```

Current output should show 27 active and mapped attractions, 18 categories,
50 activities, 13 Wikipedia enrichments and 6 Wikivoyage enrichments.

### 3. Show genuine attraction records, categories and activities

```cmd
docker exec wandaraya-postgres psql -U postgres -d wandaraya -P pager=off -c "SELECT a.id,a.name,d.name AS district,a.city,a.latitude,a.longitude,COALESCE(string_agg(DISTINCT c.name, ', '), '') AS categories,COALESCE(string_agg(DISTINCT act.name, ', '), '') AS activities FROM attractions a LEFT JOIN districts d ON d.id=a.district_id LEFT JOIN attraction_categories ac ON ac.attraction_id=a.id LEFT JOIN categories c ON c.id=ac.category_id LEFT JOIN attraction_activities aa ON aa.attraction_id=a.id LEFT JOIN activities act ON act.id=aa.activity_id GROUP BY a.id,a.name,d.name,a.city,a.latitude,a.longitude ORDER BY a.id LIMIT 10;"
```

Useful records include Galle Dutch Fort, Sri Dalada Maligawa, Yala National
Park, Dambulla Cave Temple and Sri Pada / Adam's Peak.

### 4. Show embedding and Qdrant index state

```cmd
docker exec wandaraya-api python -c "from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService; from qdrant_client import QdrantClient; c=QdrantClient(url='http://qdrant:6333'); print({'model':AttractionEmbeddingService.MODEL_NAME,'dimension':AttractionEmbeddingService.EXPECTED_DIMENSION,'collection_exists':c.collection_exists('sri_lanka_attractions'),'points_count':c.count('sri_lanka_attractions',exact=True).count})"
```

Expected: model `BAAI/bge-large-en-v1.5`, dimension `1024`, collection exists,
and 27 points.

### 5. Show real weather coverage and persisted research forecasts

```cmd
docker exec wandaraya-postgres psql -U postgres -d wandaraya -P pager=off -c "SELECT COUNT(*) AS weather_month_rows,COUNT(DISTINCT district_id) AS districts_with_weather,MIN(observation_date) AS first_month,MAX(observation_date) AS last_month,COUNT(rainfall_mm) AS rainfall_values,COUNT(temperature_min_c) AS tmin_values,COUNT(temperature_max_c) AS tmax_values FROM district_weather_monthly; SELECT target,model_name,COUNT(*) AS runs,SUM(CASE WHEN production_approved THEN 1 ELSE 0 END) AS approved_runs FROM weather_model_runs GROUP BY target,model_name ORDER BY target,model_name; SELECT COUNT(*) AS forecasts,MIN(forecast_month) AS first_forecast_month,MAX(forecast_month) AS last_forecast_month FROM weather_forecasts;"
```

Current values: 873 weather rows, 16 districts, 2021-01 to 2025-10, 43 model
runs, 129 persisted research forecasts from 2025-11 through 2026-01, and zero
approved runs.

### 6. Show model-selection evidence without retraining

```cmd
docker exec wandaraya-api python -c "import json; d=json.load(open('data/weather/reports/backtesting/model_selection_validation.json')); from collections import Counter; print('series:',len(d['series'])); print('evidence:',dict(Counter(x['evidence_status'] for x in d['series']))); print('candidate:',dict(Counter(x.get('provisional_candidate') or 'none' for x in d['series']))); [print(x['target'],x['provisional_candidate'],x['mae_comparison']) for x in d['series'] if x['district_id']==78]"
```

Current evidence: 29 eligible for review, 2 limited evidence and 12
insufficient evidence. Candidate count: 21 climatology, 10 Prophet, 12 none.

### 7. Show final validation and integrity

```cmd
docker exec wandaraya-api python -m app.weather_model.validation.end_to_end_report --run-tests --airflow-import-status passed
```

This is a controlled validation run. Expected summary: `conditionally_ready`,
204 passed, 0 failed, 0 skipped; 58 valid artifact checksums; zero production
approvals.

### 8. Demonstrate weather behavior and Airflow safely

```cmd
docker exec wandaraya-api python -m pytest tests/weather_model/test_end_to_end_weather_pipeline.py -v
docker exec wandaraya-airflow airflow dags list-import-errors
docker exec wandaraya-airflow airflow dags list
```

The Airflow import-error command should say `No data found`; the four weather
DAGs should have `is_paused=True`. Explain that their safe test executions
skipped when locations, verified import configuration and cache requests were
absent, while training remained dry-run.

## Knowledge Base scripts: safest order

Run the discovery command **without** `--ingest` first. It calls Google Places,
so it requires a configured API key and may consume provider quota, but it does
not change PostgreSQL or Qdrant.

```cmd
docker exec -it wandaraya-api python -m scripts.test_attraction_discovery
```

Its useful demonstration output is: raw Google results, unique place IDs,
already-known IDs, and new IDs. Only after reviewing those new IDs, allow the
bounded write operation below. It ingests at most three new places through the
full pipeline: normalize, validate, district resolve, deduplicate, enrich,
map categories/activities, embed and Qdrant upsert.

```cmd
docker exec -it wandaraya-api python -m scripts.test_attraction_discovery --ingest
```

For a preconfigured set of Google Place IDs, this script also writes data and
may refresh existing records. Use it only when those IDs are intentional:

```cmd
docker exec -it wandaraya-api python -m scripts.test_attraction_ingestion_pipeline
```

These are useful read/diagnostic demonstrations. The embedding/search scripts
may take time on their first execution because BGE-large has to be loaded:

```cmd
docker exec -it wandaraya-api python -m scripts.test_embedding
docker exec -it wandaraya-api python -m scripts.test_qdrant_indexing
docker exec -it wandaraya-api python -m scripts.test_semantic_retrieval
```

`test_qdrant_indexing` upserts attraction ID 1, so it is an idempotent index
write rather than a read-only check. Do not present `evaluate_semantic_retrieval`
as a working demo until its `evaluation` module and labelled retrieval dataset
are present in this repository and the script has been successfully run.

## Swagger endpoints now available

Open <http://localhost:8000/docs> and use the **Tourism Knowledge Base** group:

```text
GET /api/v1/knowledge-base/status
GET /api/v1/knowledge-base/attractions
GET /api/v1/knowledge-base/attractions/nearby
GET /api/v1/knowledge-base/attractions/{attraction_id}
GET /api/v1/knowledge-base/categories
GET /api/v1/knowledge-base/districts
GET /api/v1/knowledge-base/sources
GET /api/v1/knowledge-base/quality
GET /api/v1/knowledge-base/semantic-search
```

Example calls after FastAPI reloads:

```cmd
curl "http://localhost:8000/api/v1/knowledge-base/status"
curl "http://localhost:8000/api/v1/knowledge-base/attractions?limit=10"
curl "http://localhost:8000/api/v1/knowledge-base/attractions/nearby?latitude=6.0304&longitude=80.2150&radius_km=5"
curl "http://localhost:8000/api/v1/knowledge-base/attractions/1"
curl "http://localhost:8000/api/v1/knowledge-base/categories"
curl "http://localhost:8000/api/v1/knowledge-base/districts"
curl "http://localhost:8000/api/v1/knowledge-base/sources"
curl "http://localhost:8000/api/v1/knowledge-base/quality"
curl "http://localhost:8000/api/v1/knowledge-base/semantic-search?query=historic%%20fort%%20and%%20cultural%%20sightseeing%%20in%%20Galle&limit=5"
```

The semantic endpoint performs BGE query embedding, Qdrant similarity search,
then PostgreSQL hydration. If BGE is not yet downloaded or Qdrant is
unavailable, it returns an explicit 503 rather than fabricated recommendations.
The existing `/internal/knowledge-base/discovery` and
`/internal/knowledge-base/refresh` endpoints are also visible in Swagger, but
remain protected by `X-Airflow-Token` because they can call providers and write
data.

## Important limitations to state plainly

1. Semantic search requires the BGE embedding model and Qdrant. Its first call
   can take longer while the embedding model is loaded; unavailable dependencies
   return an explicit error instead of fabricated recommendations.
2. Qdrant reports a client/server version compatibility warning: Python client
   1.15.1 versus server 1.18.2. The collection is accessible, but align these
   versions before production deployment.
3. PostgreSQL reports a collation-version mismatch. This should be handled in a
   planned maintenance window; do not change collation during the demonstration.
4. No long-range model forecast is production-available because approval count
   is zero. This is correct governance behavior, not a failed forecast.
5. The dataset covers 16 districts, not all 25. District averages also do not
   model every local elevation or microclimate.

## One-minute summary

“I built a hybrid Sri Lanka tourism Knowledge Base that stores structured and
geographic attraction data in PostgreSQL/PostGIS and semantic representations
in Qdrant using BGE-large 1024-dimensional embeddings. I also implemented a
weather research pipeline for 16 districts. It compares Prophet with monthly
climatology and seasonal-naive baselines through rolling-origin backtesting,
then protects candidate models with evidence, checksums and manual approval.
The Weather Context Layer translates trustworthy weather into explainable,
activity-specific 0–1 suitability without fabricating unavailable information.
The next research step is integrating it with the other four context dimensions
in the final re-ranker.”
