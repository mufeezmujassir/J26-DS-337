# WANDARAYA Climate Source Selection & Overlapping Dataset Policy

## 1. Architectural Scope & Purpose
WANDARAYA maintains multiple versioned climate datasets derived from the NASA POWER Daily API v2.10.0. To prevent double-counting of overlapping time periods (specifically the calendar year 2024, which is present in both the 2024 pilot and the 2010–2025 historical series), this document defines authoritative dataset selection rules for downstream research layers.

---

## 2. Inventory of Registered Climate Dataset Versions

| Dataset Version | Scope | Reference Period | Observation Count | Grid Cell Identifiers | Target Consumers |
|---|---|---|---|---|---|
| `nasa_power_daily_v2.10.0_2024_pilot` | 6 Pilot Attraction Coordinates | 2024-01-01 to 2024-12-31 | 2,196 | `provider_coordinate:{attraction_id}` | Pilot benchmark & legacy replication |
| `nasa_power_daily_v2.10.0_historical_2010_2025_batch01` | 3 Attraction Coordinates (Galle Fort, Sigiriya, Horton Plains) | 2010-01-01 to 2025-12-31 | 17,532 | `provider_coordinate:{attraction_id}` | Attraction-specific high-resolution analysis |
| `nasa_power_daily_v2.10.0_historical_2010_2025_batch02` | 25 District Representative Coordinates | 2010-01-01 to 2025-12-31 | 146,100 | `district_representative:{district_id}` | National Seasonality Context Layer & Stage 12.4C Baselines |

---

## 3. Disambiguation & Source Selection Hierarchy

### Rule 1: National District Climatology (Default for Stage 12.4C)
- When computing monthly climatologies, long-term trends, or seasonality metrics by district, queries **MUST filter strictly by**:
  `dataset_version = 'nasa_power_daily_v2.10.0_historical_2010_2025_batch02'`
- Under no circumstances shall Batch 01 attraction observations or 2024 pilot observations be pooled into district averages.

### Rule 2: Attraction Micro-Location Analysis
- When evaluating specific attraction weather histories where an exact attraction coordinate sample was collected (Attractions 1, 16, 24):
  - Prefer `nasa_power_daily_v2.10.0_historical_2010_2025_batch01` via `climate_attraction_mappings`.
  - For attractions without a dedicated attraction sample, fall back to the district representative sample from `batch02` via the attraction's `district_id`.
  - Disclose `geographic_confidence = 'DISTRICT_CENTROID_REPRESENTATIVE'` vs `'EXPERIMENTAL_COARSE_GRID'`.

### Rule 3: Isolation of 2024 Pilot
- The 2024 pilot dataset (`nasa_power_daily_v2.10.0_2024_pilot`) is an immutable research baseline. It MUST NOT be combined with historical batches for 2024.
- Any time-series aggregation spanning 2024 MUST select observations exclusively from either the historical series OR the pilot, never both.

### Rule 4: Non-Interchangeability of Coordinates
- Even if an attraction falls within a district (e.g. Galle Dutch Fort at 6.0305°N, 80.2150°E inside Galle District), its coordinate sample does not replace the district representative coordinate (6.1582°N, 80.5194°E). Both maintain distinct grid cell records and separate historical series.

---

## 4. SQL Implementation Pattern

```sql
-- Correct pattern for District 78 (Galle) Climatology:
SELECT
    EXTRACT(MONTH FROM o.observation_date) AS month,
    AVG(o.temperature_mean_c) AS mean_t2m,
    AVG(o.precipitation_mm) AS mean_precip
FROM climate_daily_observations o
JOIN climate_district_mappings m ON o.grid_cell_id = m.grid_cell_id AND o.dataset_version_id = m.dataset_version_id
JOIN climate_dataset_versions d ON m.dataset_version_id = d.id
WHERE m.district_id = 78
  AND d.product_version = 'nasa_power_daily_v2.10.0_historical_2010_2025_batch02'
GROUP BY EXTRACT(MONTH FROM o.observation_date)
ORDER BY month;
```
