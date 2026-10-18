# Weather Airflow pipeline (Stage 9.8.11)

The four weather DAGs orchestrate existing WANDARAYA components. They are all
paused when first discovered and do not change model approval state.

| DAG | Default schedule (UTC) | Action |
| --- | --- | --- |
| `weather_live` | every three hours (`0 */3 * * *`) | Fetch configured live locations and cache only validated responses. |
| `weather_historical` | 02:00 on the first of each month | Run an explicitly configured verified append-only import. |
| `weather_model_train` | 03:00 on the second of each month | Run the Stage 9.8.8 candidate trainer in dry-run mode by default. |
| `weather_predictions_cache` | 04:00 every Monday | Cache reliability-checked live or production-approved forecasts. |

## Configuration

Keep credentials in `.env`; never put provider keys in DAG files. The following
optional settings control the pipeline:

```env
# A JSON list, for example: [{"district_id":78,"latitude":6.0535,"longitude":80.2210}]
WEATHER_LIVE_LOCATIONS_JSON=[]
WEATHER_LIVE_RATE_LIMIT_SECONDS=1

# Historical imports are disabled until both values are deliberately supplied.
WEATHER_HISTORICAL_UPDATE_POLICY=verified_append_only
WEATHER_HISTORICAL_IMPORT_COMMAND=python -m scripts.your_verified_import

# Remains false unless a reviewed operational decision enables candidate training.
WEATHER_TRAIN_EXECUTE=false

# A JSON list of district/target/date requests. Missing or unapproved models return unavailable.
WEATHER_PREDICTION_CACHE_REQUESTS_JSON=[]
```

Each schedule can be changed without editing a DAG using `WEATHER_LIVE_SCHEDULE`,
`WEATHER_HISTORICAL_SCHEDULE`, `WEATHER_MODEL_TRAIN_SCHEDULE`, or
`WEATHER_PREDICTIONS_CACHE_SCHEDULE`.

## Start and verify

From the repository root in PowerShell:

```powershell
docker compose up -d --build --force-recreate airflow-metadata airflow
docker compose exec airflow airflow dags list
docker compose exec airflow airflow dags list-import-errors
```

Open the Airflow UI at <http://localhost:8080>. `standalone` creates the local
administrator during initial startup; manage or reset that account inside the
Airflow container before exposing the UI outside a development environment.

Verify that all four DAGs are initially paused before enabling any of them:

```powershell
docker compose exec airflow airflow dags list | Select-String weather_
```

## Manual runs

Only unpause a DAG after its required configuration has been reviewed. For
example:

```powershell
docker compose exec airflow airflow dags unpause weather_live
docker compose exec airflow airflow dags trigger weather_live
docker compose exec airflow airflow dags trigger weather_historical
docker compose exec airflow airflow dags trigger weather_model_train
docker compose exec airflow airflow dags trigger weather_predictions_cache
```

The prediction-cache DAG uses the Stage 9.8.9 reliability service. It never
uses an unapproved candidate model, substitutes another district, or turns a
monthly rainfall total into daily rainfall. With the current zero approved
models, long-range requests are expected to be explicitly unavailable unless a
valid live-provider forecast covers the requested date.
