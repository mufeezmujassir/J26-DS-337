# WANDARAYA Weather Context Layer

## Scope and architecture

Component 1, Layer 2 is an independent weather-context dimension. It does not
rank attractions by itself and does not implement time-of-day, holiday,
seasonality, or group-emotion dimensions.

```text
Verified historical observations
  -> preprocessing / district monthly aggregation
  -> rolling-origin backtesting and model-selection evidence
  -> manual registry review -> immutable candidate artifacts
  -> ForecastService (live provider or approved artifact only)
  -> WeatherContextService / WeatherSuitabilityEngine
  -> WeatherContextDimension contract for a future Context Re-Ranker
```

The older calibrated 0–100 tourism suitability flow remains separate. The
Stage 9.8.10 `WeatherSuitabilityEngine` exposes an explainable 0–1 weather-only
dimension, and `app.recommendation.context_dimensions.weather_context_contract`
adapts it without applying any re-ranking weights.

## Data and model methodology

Historical inputs are monthly district observations imported through the
existing normalizers, validators, station/district resolution, and aggregation
pipeline. The coverage audit is stored in
`data/weather/reports/backtesting/district_coverage_audit.json`.

Candidate models are Prophet and monthly climatology. They are compared using
rolling-origin backtesting and model-selection evidence. Temperature training
uses the existing training-only missing-aware policy with **95%** minimum
coverage. Rainfall requires complete verified observations: missing rainfall is
never interpolated.

Candidate artifacts contain training provenance, configuration, a deterministic
version, and SHA-256 checksum. They remain unapproved until an explicit,
auditable registry decision. A candidate is never a production forecast merely
because it exists on disk.

## Forecast reliability and scoring rules

`ForecastService` uses live OpenWeather data only for dates within its five-day
provider horizon. It uses a model artifact only when its registry approval,
evidence fingerprint, manifest, version, and checksum all remain valid.
Otherwise it returns `unavailable`.

Daily or three-hourly-aggregated provider rainfall can affect activity scores.
Monthly model rainfall totals and historical monthly means are informational
only: they are never converted into daily rain, rain probability, or a daily
rainfall penalty. Unknown or unreliable weather produces `status="unknown"`
with a null suitability score.

The supported weather activity profiles are hiking, beach, wildlife safari,
heritage site, water activities, and indoor attraction. Scores are deterministic
and explain their temperature, rainfall, and precipitation-probability effects.

## Airflow workflows

All DAGs are paused on discovery and use UTC schedules. See
`docs/weather_airflow_pipeline.md` for exact configuration and operating
commands.

| DAG | Default UTC schedule | Safe default |
| --- | --- | --- |
| `weather_live` | `0 */3 * * *` | Skips until locations are configured; caches only validated provider responses. |
| `weather_historical` | `0 2 1 * *` | Skips unless a verified append-only import command is explicitly configured. |
| `weather_model_train` | `0 3 2 * *` | Runs candidate-training dry-run unless `WEATHER_TRAIN_EXECUTE=true`. |
| `weather_predictions_cache` | `0 4 * * 1` | Caches only live or approved-model results; unavailable is retained explicitly. |

An imported DAG or successful trigger is not evidence that its task executed
successfully. Inspect a task instance state and its task log in Airflow before
recording an operational run as successful.

## Validation and report

Run the weather test suite and write a factual machine-readable report:

```cmd
docker exec wandaraya-api python -m app.weather_model.validation.end_to_end_report --run-tests
```

Output:

```text
data/weather/reports/validation/weather_layer_end_to_end_validation.json
```

The report records exact pytest results, existing coverage-audit information,
registry approval counts, artifact checksum results, static DAG configuration,
and limitations. It intentionally marks Airflow task execution as unverified;
obtain that evidence from Airflow task logs after a deliberate run.

Verify Airflow imports separately:

```cmd
docker exec wandaraya-airflow airflow dags list-import-errors
docker exec wandaraya-airflow airflow dags list
```

## Operational troubleshooting

- `ModuleNotFoundError: geoalchemy2`: rebuild only Airflow after dependency
  changes: `docker compose build airflow`, then
  `docker compose up -d --no-deps --force-recreate airflow`.
- No `weather_live` output: configure `WEATHER_LIVE_LOCATIONS_JSON` and a valid
  OpenWeather API key; never put the key in a DAG.
- Historical DAG skips: this is expected until both
  `WEATHER_HISTORICAL_UPDATE_POLICY=verified_append_only` and an explicit
  verified import command are configured.
- Long-range result is unavailable: this is expected while no model is manually
  production-approved, or when artifact integrity/evidence validation fails.
- Do not solve missing historical rainfall by interpolation or by copying another
  district's value. Recover a verified original observation instead.
