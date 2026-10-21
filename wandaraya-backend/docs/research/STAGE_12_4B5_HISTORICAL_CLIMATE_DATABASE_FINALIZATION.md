# Stage 12.4B.5 — Historical Climate Database Persistence, Transaction Integrity, and National Climate Dataset Finalization

## 1. Scientific Objective
This research milestone establishes the complete, validated, and queryable historical climate database foundation for WANDARAYA's Seasonality Context Layer. The operational objective is to persist 16 years (2010–2025) of daily meteorological observations across 25 district representatives and 3 key attraction micro-coordinates into PostgreSQL, ensuring transaction atomicity, relational integrity, zero duplicate records, and full preservation of the pre-existing 2024 pilot baseline.

---

## 2. Data Source Attribution & Product Provenance
- **Provider:** NASA Prediction Of Worldwide Energy Resources (POWER) Daily API v2.10.0.
- **Endpoint:** `https://power.larc.nasa.gov/api/temporal/daily/point`
- **Data Heritage:** Built on satellite observations and meteorological data assimilation models, specifically:
  - CERES SYN1deg (Synoptic 1-degree) for surface solar irradiance.
  - NASA GMAO MERRA-2 (Modern-Era Retrospective analysis for Research and Applications, Version 2) for atmospheric variables.
- **Attribution Text:** NASA POWER
- **Community:** Agroclimatology (`AG`)
- **Time Standard:** Coordinated Universal Time (UTC)
- **Scientific Clarification:** NASA POWER is a coarse-grid satellite/assimilation product (~0.5° × 0.5° resolution, approximately 50 km × 50 km). It does NOT represent in-situ physical ground weather station measurements, nor is it raw ERA5/ERA5-Land reanalysis.

---

## 3. Climate Variables & Measurement Units

| Parameter | Research Identifier | Description | Native Unit | Normalized Stored Unit | Completeness |
|---|---|---|---|---|---|
| `T2M` | `temperature_mean_c` | Daily mean temperature at 2 meters | °C | °C | 100.0% (0 NULLs) |
| `T2M_MAX` | `temperature_max_c` | Daily maximum temperature at 2 meters | °C | °C | 100.0% (0 NULLs) |
| `T2M_MIN` | `temperature_min_c` | Daily minimum temperature at 2 meters | °C | °C | 100.0% (0 NULLs) |
| `PRECTOTCORR` | `precipitation_mm` | Corrected daily total precipitation | mm/day | mm/day | 100.0% (0 NULLs) |
| `RH2M` | `relative_humidity_pct` | Relative humidity at 2 meters | % | % | 100.0% (0 NULLs) |
| `WS10M` | `wind_speed` | Wind speed at 10 meters | m/s | m/s | 100.0% (0 NULLs) |
| `ALLSKY_SFC_SW_DWN` | `solar_radiation` | All sky surface shortwave downward irradiance | MJ/m²/day | MJ/m²/day | 100.0% (0 NULLs) |

---

## 4. Sampling Architecture & Coordinate Isolation
A total of **28 coordinate points** are registered across Sri Lanka:
1. **Historical Batch 01 (3 Attraction Coordinates):**
   - Sample `historic_1`: Galle Dutch Fort (6.0305°N, 80.2150°E, District 78 Galle)
   - Sample `historic_16`: Sigiriya Ancient City (7.9456°N, 80.7616°E, District 74 Anuradhapura)
   - Sample `historic_24`: Pedro Estate / Nuwara Eliya (6.8094°N, 80.8023°E, District 92 Nuwara Eliya)
   - Records: 3 samples × 5,844 days = **17,532 daily observations**
2. **Historical Batch 02 (25 District Representatives):**
   - 25 representative coordinates representing all districts in Sri Lanka (Districts 73 to 97).
   - PostGIS containment validation: All 25 coordinates verified to lie inside their respective district MultiPolygon boundaries via `ST_Covers(boundary, ST_SetSRID(ST_MakePoint(lon, lat), 4326))`.
   - Records: 25 samples × 5,844 days = **146,100 daily observations**
3. **Total Historical Records Persisted:** **163,632 observations**
4. **Preserved 2024 Pilot:** **2,196 observations** (6 samples × 366 days in 2024)
5. **Grand Total in Database:** **165,828 daily observations**

---

## 5. Relational Schema & Migration Implementation
To cleanly separate district-representative relationships from attraction-specific point mappings, an additive Alembic migration `f78a9b0c1d2e_add_climate_district_mappings.py` was introduced, establishing the `climate_district_mappings` table:

```
climate_dataset_versions (id, product_version, ...)
  │
  ├──< climate_grid_cells (id, dataset_version_id, source_grid_identifier, geometry, ...)
  │      │
  │      ├──< climate_daily_observations (id, dataset_version_id, grid_cell_id, observation_date, ...)
  │      │
  │      ├──< climate_attraction_mappings (attraction_id, dataset_version_id, grid_cell_id, ...)
  │      │      └──> attractions (id)
  │      │
  │      └──< climate_district_mappings (district_id, dataset_version_id, grid_cell_id, ...)
  │             └──> districts (id)
  │
  └──< climate_ingestion_runs (id, dataset_version_id, status, records_accepted, ...)
```

### Table Inventory & Constraints:
- `climate_dataset_versions`: Unique constraint on `(provider_name, product_name, product_version)`.
- `climate_grid_cells`: Unique constraint on `(dataset_version_id, source_grid_identifier)`. Point geometry indexed with PostGIS GiST index.
- `climate_daily_observations`: Unique constraint on `(dataset_version_id, grid_cell_id, observation_date)`. Foreign keys cascade/restrict properly.
- `climate_district_mappings`: Unique constraint on `(district_id, dataset_version_id)`. Indexes on `district_id`, `dataset_version_id`, and `grid_cell_id`.
- `climate_attraction_mappings`: Unique constraint on `(attraction_id, dataset_version_id)`.
- `climate_ingestion_runs`: Logs run start, completion, records received, accepted, and rejected.

---

## 6. Database Verification: Before vs. After Ingestion

| Metric / Table | Baseline (Before 12.4B.5) | Final (After 12.4B.5) | Delta | Integrity Verification |
|---|---|---|---|---|
| `climate_dataset_versions` | 1 | 3 | +2 | Pilot, Batch01, Batch02 distinct |
| `climate_grid_cells` | 6 | 34 | +28 | 6 pilot + 3 batch01 + 25 batch02 |
| `climate_daily_observations` | 2,196 | 165,828 | +163,632 | 100% matched expected count |
| `climate_attraction_mappings` | 6 | 9 | +3 | 6 pilot + 3 batch01 |
| `climate_district_mappings` | 0 | 28 | +28 | 25 batch02 + 3 batch01 |
| `climate_ingestion_runs` | 1 | 3 | +2 | All runs logged with SUCCEEDED |
| `district_weather_monthly` | 873 | 873 | 0 | Preserved unchanged |
| `weather_forecasts` | 129 | 129 | 0 | Preserved unchanged |
| `weather_model_runs` | 43 | 43 | 0 | Preserved unchanged |
| `weather_readings` | 1,162 | 1,162 | 0 | Preserved unchanged |
| `weather_stations` | 23 | 23 | 0 | Preserved unchanged |

---

## 7. Transaction Strategy, Idempotency & Recovery
1. **Transaction Encapsulation:**
   - Ingestion was executed using atomic SQLAlchemy session blocks (`async with session.begin():`).
   - If any integrity error or parsing failure occurred, the transaction rolled back without committing partial observations.
2. **Idempotent Upsert Strategy:**
   - Daily observations use `ON CONFLICT (dataset_version_id, grid_cell_id, observation_date) DO NOTHING`.
   - Grid cells and dataset versions use idempotent `ON CONFLICT ... DO UPDATE`.
3. **Idempotency Verification:**
   - A full re-run was executed against the database after initial persistence.
   - Result: 0 duplicate records inserted, observation count remained exactly 165,828.

---

## 8. Query Performance Analysis
A representative climatology query (retrieving 1 year of daily climate observations for District 78 Galle joining `climate_district_mappings` and `climate_daily_observations`) was analyzed via `EXPLAIN ANALYZE`:
- **Execution Plan:** Nested Loop using `uq_climate_district_mapping` btree index and `uq_climate_daily_observation` btree index.
- **Execution Time:** **0.384 ms** (sub-millisecond).
- **Conclusion:** Existing btree indexes on `(district_id, dataset_version_id)` and `(dataset_version_id, grid_cell_id, observation_date)` provide optimal sub-millisecond retrieval suitable for real-time recommendation agent inference.

---

## 9. Read-Only Data Access Layer (`HistoricalClimateService`)
Implemented in `app/climate/services/historical_climate.py`:
- `get_district_daily(district_id, start_date, end_date, dataset_version)`: Retrieves time series for a district.
- `get_sample_daily(grid_cell_id, start_date, end_date)`: Retrieves observations for a specific sample.
- `get_district_observations_by_month(district_id, month, dataset_version)`: Retrieves all historical days across 16 years for a specific calendar month (e.g. all Januaries).
- `get_district_yearly_summary(district_id, start_year, end_year, dataset_version)`: Computes yearly aggregations (mean T2M, total rain, min/max temps).
- `get_quality_statistics(dataset_version)`: Returns total and validated record counts.
- `get_dataset_provenance(dataset_version)`: Retrieves dataset metadata and units.
- `get_source_geographic_uncertainty(district_id, dataset_version)`: Retrieves coordinate confidence and metadata.
- `get_available_date_coverage(dataset_version)`: Returns start date, end date, and distinct date count.
- `list_dataset_versions()`: Lists all registered climate dataset versions.

---

## 10. Automated Test Results
All 20 test cases executed successfully via `scripts/run_stage12_4b5_tests.py`:
- Test 01: Historical manifest parsing — **PASS**
- Test 02: Source checksum verification — **PASS**
- Test 03: Dataset version registration — **PASS**
- Test 04: Sample identity registration — **PASS**
- Test 05: District mapping integrity — **PASS**
- Test 06: Daily observation parsing — **PASS**
- Test 07: Missing-value conversion — **PASS**
- Test 08: Variable-level quality checks — **PASS**
- Test 09: Date-range completeness — **PASS**
- Test 10: Leap-year handling — **PASS**
- Test 11: Duplicate prevention — **PASS**
- Test 12: Transaction rollback — **PASS**
- Test 13: Interrupted ingestion recovery — **PASS**
- Test 14: Idempotent rerun — **PASS**
- Test 15: Preservation of the 2024 pilot — **PASS**
- Test 16: Preservation of unrelated weather tables — **PASS**
- Test 17: Dataset-version isolation — **PASS**
- Test 18: District boundary validation — **PASS**
- Test 19: Read-only historical climate queries — **PASS**
- Test 20: PostgreSQL readback verification — **PASS**

---

## 11. Known Limitations
1. **Spatial Granularity:** One representative coordinate per district does not capture local microclimates (e.g. Nuwara Eliya vs. low-lying areas in the Central province). Mountainous and coastal districts will benefit from additional grid sampling in future stages.
2. **Reanalysis/Satellite Model Nature:** NASA POWER values are model/satellite derived, not direct physical ground station rain-gauge observations.
3. **Infrastructure Collation Warning:** The PostgreSQL database was initialized with collation version 2.41, while the current container OS reports 2.31. This warning remains preserved and untouched per system instructions.

---

## 12. Reproducibility Commands
To verify the database state or rerun tests at any time:

```bash
# 1. Run source integrity and quality checks
docker exec wandaraya-api-cutover python -m scripts.validate_stage12_4b5_sources

# 2. Run the historical climate ingestion (idempotent)
docker exec wandaraya-api-cutover python -m scripts.ingest_stage12_4b5_historical --batch all

# 3. Run the automated test suite
docker exec wandaraya-api-cutover python -m scripts.run_stage12_4b5_tests
```

---

## 13. Research Progression
**Current Stage Status:** `HISTORICAL_CLIMATE_DATASET_PERSISTED_VERIFIED`  
**Next Research Milestone:** **Stage 12.4C — Monthly Climate Knowledge Base and Explainable Seasonality Baselines**.
