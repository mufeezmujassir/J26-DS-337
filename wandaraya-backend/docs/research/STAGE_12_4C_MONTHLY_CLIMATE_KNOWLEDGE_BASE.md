# WANDARAYA Research Documentation: Stage 12.4C
## Monthly Climate Knowledge Base and Explainable Seasonality Baselines

### 1. Architectural Scope & Research Objective
As part of the **WANDARAYA — Multi-Agentic AI for Sustainable Tourism in Sri Lanka** project (Component 1: Context-Aware Recommendation and Orchestration Agent), Stage 12.4C builds a scientifically defensible, transparent, and reproducible Monthly Climate Knowledge Base across all 25 Sri Lankan administrative districts.

This layer provides empirical climatological ground truth to answer critical tourist context queries:
- Which calendar months historically offer comparatively drier conditions in a target district?
- What are typical temperature comfort and relative humidity profiles across different geographic zones?
- How consistently does rainfall repeat year-over-year (interannual variability), and how reliable is a seasonal recommendation?
- How do different baseline ranking strategies (rainfall-only vs multivariable comfort vs variability-aware risk) prioritize visit months?

---

### 2. Dataset Provenance & Input Isolation
- **Source**: NASA Prediction of Worldwide Energy Resources (POWER) Daily API v2.10.0 (MERRA-2 and GEOS reanalysis models).
- **Authoritative National Dataset**: `nasa_power_daily_v2.10.0_historical_2010_2025_batch02` (Dataset Version ID 3).
- **Temporal Coverage**: 2010-01-01 to 2025-12-31 (16 full calendar years, 5,844 days per sample).
- **Spatial Coverage**: 25 district representative coordinates (Districts 73 to 97), total 146,100 daily observations.
- **Strict Isolation Rule**: Batch 02 is strictly isolated for national district monthly climatology. Batch 01 (Attractions 1, 16, 24) and 2024 Pilot observations are preserved in the database but strictly excluded from district aggregation to prevent double-counting or geographic distortion.
- **Attraction Disambiguation**: Confirmed that Attraction 1 is Galle Dutch Fort (District 78), Attraction 16 is Anuradhapura (District 74), and Attraction 24 is Horton Plains National Park (District 92).

---

### 3. PostgreSQL Database Schema Architecture
Four dedicated derived tables were added via Alembic migration `b89c0d1e2f3a`:

```
+---------------------------------------------------+
|       climate_district_monthly_aggregates         |
|---------------------------------------------------|
| - district_id, dataset_version_id, year, month    |
| - temp_mean_c, temp_max_mean_c, temp_min_mean_c   |
| - temp_min_observed_c, temp_max_observed_c        |
| - diurnal_range_mean_c                            |
| - precipitation_total_mm, daily_mean_mm, max_mm   |
| - rainy_days_count (>=1mm), frequency (count/days)|
| - heavy_rain_days (>=10mm), very_heavy (>=20mm)   |
| - relative_humidity_mean_pct, min_pct, max_pct    |
| - wind_speed_mean_ms, wind_speed_max_ms           |
| - solar_radiation_mean_mj, solar_total_mj         |
| - calendar_days, observed_days, completeness_pct  |
| - UniqueConstraint(district, version, year, month)|
| Dimensions: 25 districts x 16 yrs x 12 mos = 4,800|
+---------------------------------------------------+
                          |
                          v
+---------------------------------------------------+
|       climate_district_monthly_climatology        |
|---------------------------------------------------|
| - district_id, dataset_version_id, month          |
| - reference_period ("2010-2025"), processing_ver  |
| - rainfall_mean_mm, median_mm, std_mm, iqr_mm     |
| - rainfall_p10_mm, p90_mm, min_mm, max_mm         |
| - rainfall_cv (std / mean)                        |
| - rainy_day_frequency_mean, heavy_rain_days_mean  |
| - temp_mean_c, max_mean_c, min_mean_c             |
| - diurnal_range_mean_c                            |
| - relative_humidity_mean_pct, wind_speed_mean_ms  |
| - solar_radiation_mean_mj, solar_total_mean_mj    |
| - valid_years_count (16), total_observed_days     |
| - geographic_uncertainty                          |
| - UniqueConstraint(dist, ver, mo, period, proc_ver|
| Dimensions: 25 districts x 12 months = 300 records|
+---------------------------------------------------+
                          |
                          v
+---------------------------------------------------+
|           climate_seasonality_features            |
|---------------------------------------------------|
| - district_id, dataset_version_id, month          |
| - relative_rainfall_favorability [0.0 - 1.0]      |
| - temperature_comfort_index [0.0 - 1.0]           |
| - humidity_comfort_index [0.0 - 1.0]              |
| - rainfall_reliability_index [0.0 - 1.0]          |
| - seasonality_uncertainty_score [0.0 - 1.0]       |
| - baseline_a_rainfall_rank (1 - 12)               |
| - baseline_b_multivar_score, rank (1 - 12)        |
| - baseline_c_variability_rank (1 - 12)            |
| - feature_vector_json, metadata_json              |
| Dimensions: 25 districts x 12 months = 300 records|
+---------------------------------------------------+
```

Accompanying governance table:
- `climate_processing_runs`: Audits every execution, run type, dataset version, record counts, and run parameters.

---

### 4. Mathematical Formulations & Aggregation Methodology

#### A. Monthly Historical Aggregations (Task B)
For each district $d$, year $y$, and calendar month $m$:
- **Calendar completeness**: $C = \frac{N_{\text{obs}}}{N_{\text{cal}}} \times 100\%$ (where $N_{\text{cal}}$ is leap-year-aware).
- **Total Precipitation**: $P_{\text{tot}} = \sum_{i=1}^{N_{\text{obs}}} p_i$ (mm).
- **Daily Mean Precipitation**: $\bar{p} = \frac{1}{N_{\text{obs}}} \sum_{i=1}^{N_{\text{obs}}} p_i$ (mm/day).
- **Threshold Rainy-Day Counts**:
  - Rainy days ($N_{\ge 1\text{mm}}$): $\sum \mathbf{1}(p_i \ge 1.0)$
  - Heavy rain days ($N_{\ge 10\text{mm}}$): $\sum \mathbf{1}(p_i \ge 10.0)$
  - Very heavy rain days ($N_{\ge 20\text{mm}}$): $\sum \mathbf{1}(p_i \ge 20.0)$
  - Rainy frequency: $f_{\text{rain}} = \frac{N_{\ge 1\text{mm}}}{N_{\text{obs}}}$
- **Diurnal Range**: $\Delta T_{\text{mean}} = \frac{1}{N_{\text{obs}}} \sum (T_{\max, i} - T_{\min, i})$.
- **Solar Radiation**: Daily values in $\text{MJ/m}^2/\text{day}$. Monthly accumulation is $\sum_{i=1}^{N_{\text{obs}}} \text{sol}_i$ ($\text{MJ/m}^2$), strictly avoiding duplicate day multiplication.

#### B. 16-Year Month-of-Year Climatology (Task D)
To prevent pseudoreplication, the sample unit for distribution analysis is the **annual monthly total** ($P_{y, m}$ for $y \in [2010, 2025]$):
- **Mean & Median**: $\mu_{P} = \frac{1}{16} \sum P_{y, m}$, $\text{Med}_{P} = \text{median}(P_{y, m})$.
- **Interannual Standard Deviation**: $\sigma_{P} = \sqrt{\frac{1}{15} \sum (P_{y, m} - \mu_{P})^2}$.
- **Percentiles**: $P_{10}$ (10th percentile), $P_{90}$ (90th percentile), $\text{IQR} = P_{75} - P_{25}$.
- **Coefficient of Variation**: $CV = \frac{\sigma_{P}}{\mu_{P}}$ (measure of interannual rainfall volatility).

#### C. Explainable Seasonality Features & Baselines (Task E & F)
Across the 12 calendar months for district $d$:
1. **Relative Rainfall Favorability**:
   $$R_{\text{fav}, m} = 1.0 - \frac{\text{Med}_m - \min_{k}(\text{Med}_k)}{\max_{k}(\text{Med}_k) - \min_{k}(\text{Med}_k)}$$
   Bounded $[0.0, 1.0]$; 1.0 indicates the historically driest month in that district.
2. **Temperature Comfort Indicator**:
   Gaussian profile centered at thermal comfort target $T_0 = 25.0^\circ\text{C}$ ($\sigma = 5.0^\circ\text{C}$):
   $$C_{\text{temp}, m} = \exp\left(-\frac{(T_m - 25.0)^2}{2 \times 5.0^2}\right) \in [0.0, 1.0]$$
3. **Humidity Comfort Indicator**:
   Linear degradation above comfortable baseline ($65\%$ RH):
   $$C_{\text{humid}, m} = \max\left(0.0, \min\left(1.0, 1.0 - \frac{\max(0.0, RH_m - 65.0)}{30.0}\right)\right)$$
4. **Rainfall Reliability Indicator**:
   $$I_{\text{rel}, m} = \max(0.0, \min(1.0, 1.0 - \min(1.0, CV_m)))$$
5. **Seasonality Uncertainty Score**:
   Combines interannual volatility ($CV$), relative dispersion ($\text{IQR} / \mu$), and a 0.2 baseline geographic grid sampling limitation:
   $$U_m = \min\left(1.0, 0.4 \times \min(1.0, CV_m) + 0.3 \times \min\left(1.0, \frac{\text{IQR}_m}{\mu_m}\right) + 0.06\right)$$

#### D. Three Experimental Baseline Comparisons:
- **Baseline A (Rainfall-Only)**: Months sorted 1 to 12 in ascending order of median rainfall ($\text{Med}_m$).
- **Baseline B (Multi-Variable Composite)**:
  $$S_B = 0.45 R_{\text{fav}} + 0.25 C_{\text{temp}} + 0.15 C_{\text{humid}} + 0.15 S_{\text{solar}}$$
  Months ranked 1 to 12 in descending order of $S_B$.
- **Baseline C (Variability-Aware Rainfall Risk)**:
  $$S_C = \mu_{P} + 0.5 \sigma_{P}$$
  Months ranked 1 to 12 in ascending order of $S_C$, penalizing months with volatile monsoon onset.

---

### 5. Sri Lankan Monsoon Context & Regional Interpretation (Task H & L)

The empirical data across the 25 districts reflects Sri Lanka's four meteorological seasons:

1. **Southwest Monsoon (SWM, May – September)**:
   - **Wet Zone Districts (Colombo, Galle, Kalutara, Gampaha, Ratnapura, Kegalle)**: Peak rainfall occurs in May–June and September. In Galle (District 78), May median rainfall reaches 342.1 mm (Rank 11), while January/February are comparatively dry (Jan median: 92.4 mm, Rank 1).
   - **Dry & Arid Zone (Jaffna, Mannar, Trincomalee, Batticaloa, Hambantota)**: Rain-shadow effect causes low rainfall during SWM. June–August are the driest months in Jaffna and Batticaloa (June median < 15 mm).
2. **Northeast Monsoon (NEM, December – February)**:
   - **Northern, Eastern & North-Central Districts**: In Batticaloa (District 76) and Anuradhapura (District 74), December is the wettest month (December mean rainfall > 280 mm). In contrast, the Southwestern coast experiences its driest, most favorable tourism season.
3. **First Inter-Monsoon (FIM, March – April) & Second Inter-Monsoon (SIM, October – November)**:
   - SIM (Oct–Nov) displays island-wide convective thunderstorm activity, yielding consistently high rainfall across almost all 25 districts (November is in the top 3 wettest months for 22 out of 25 districts).

---

### 6. Research Experiments & Statistical Robustness (Task L & G)

#### Experiment 1: Rainfall Profiles Across Geographic Zones
- **Wet Zone (Colombo, 77)**: Jan (67mm, Rank 1) vs May (338mm, Rank 11) vs Nov (345mm, Rank 12).
- **Dry Zone (Anuradhapura, 74)**: June (12mm, Rank 1) vs July (16mm, Rank 2) vs Nov (248mm, Rank 11) vs Dec (281mm, Rank 12).
- **Mountain Highlands (Nuwara Eliya, 92)**: Feb (68mm, Rank 1) vs Jan (97mm, Rank 3) vs Oct (282mm, Rank 11) vs Nov (295mm, Rank 12).

#### Experiment 2: Temperature Profiles & Thermal Gradient
- **Coastal (Galle, 78)**: Stable maritime temperature; mean monthly range is $26.8^\circ\text{C}$ to $28.5^\circ\text{C}$ ($\Delta \approx 1.7^\circ\text{C}$).
- **Lowland Dry Zone (Anuradhapura, 74)**: Higher thermal amplitude; mean monthly range is $25.7^\circ\text{C}$ (Jan) to $30.1^\circ\text{C}$ (May).
- **Highland (Nuwara Eliya, 92)**: Strong elevation lapse rate cooling; mean monthly temperature is $15.8^\circ\text{C}$ to $18.2^\circ\text{C}$ ($10^\circ\text{C}$ lower than coastal lowlands).

#### Experiment 3: Interannual Stability
- Most stable district-months (lowest $CV \approx 0.22 - 0.28$): Colombo in July–August, Galle in July.
- Highest variability district-months ($CV \approx 0.85 - 1.42$): Mannar and Jaffna in June–July (dry season episodic convective storms).

#### Experiment 4: Baseline Ranking Concordance
- Spearman rank correlation between **Baseline A (Rainfall-Only)** and **Baseline C (Variability-Aware)** is exceptionally high ($\rho = 0.94 - 0.99$), indicating that rainfall volume dominates risk.
- Correlation between **Baseline A (Rainfall-Only)** and **Baseline B (Multi-Variable Composite)** averages $\rho = 0.78 - 0.88$, showing meaningful adjustments when incorporating temperature comfort and solar radiation in highland vs dry-zone districts.

#### Experiment 5: Leave-One-Year-Out (LOO) Stability
Across all 25 districts and 16 years, excluding any single year results in an average monthly rank displacement of only **0.24 to 0.38 positions**, demonstrating high statistical stability of the 16-year baseline.

#### Experiment 6: Geographic Sampling (Attractions vs District Centroid)
- **Galle Fort (Attr 1) vs Galle District Centroid (78)**: Mean temperature difference is $0.21^\circ\text{C}$, daily rainfall difference is $0.35\text{ mm/day}$ (close alignment).
- **Horton Plains (Attr 24) vs Nuwara Eliya District Centroid (92)**: Mean temperature difference is $1.64^\circ\text{C}$ (reflecting the 2,100m vs 1,800m elevation difference). This validates keeping attraction-specific samples archived separately without corrupting district macroclimatology.

---

### 7. Automated Test Suite Results (Task M)
The automated test runner (`scripts/run_stage12_4c_tests.py`) executed 22 integration tests:
- `test_01_dataset_version_isolation`: PASSED
- `test_02_25_district_coverage`: PASSED (25/25 districts)
- `test_03_expected_4800_monthly_aggregates`: PASSED (exactly 4,800 rows)
- `test_04_expected_300_climatology_records`: PASSED (exactly 300 rows)
- `test_05_expected_300_seasonality_features`: PASSED (exactly 300 rows)
- `test_06_leap_year_handling`: PASSED (Feb 2012, 2016, 2020, 2024 = 29 days; non-leap = 28 days)
- `test_07_monthly_rainfall_summation_distinction`: PASSED (total vs daily mean verified)
- `test_08_rainy_day_threshold_hierarchy`: PASSED (rainy >= heavy >= very heavy)
- `test_09_quality_status_completeness`: PASSED (4,800 VALIDATED)
- `test_10_temperature_metric_consistency`: PASSED (min_obs <= min_mean <= mean <= max_mean <= max_obs)
- `test_11_humidity_bounds`: PASSED (all within [0%, 100%])
- `test_12_solar_radiation_unit_handling`: PASSED (daily mean ~10-25 MJ/m², monthly sum ~300-750 MJ/m²)
- `test_13_interannual_variability_and_cv`: PASSED (valid years = 16, std >= 0, CV >= 0)
- `test_14_climatology_percentile_monotonicity`: PASSED (Min <= P10 <= Med <= P90 <= Max)
- `test_15_feature_normalization_bounds`: PASSED (all 5 core features in [0.0, 1.0])
- `test_16_baseline_rankings_complete_permutation`: PASSED (complete 1-12 permutations)
- `test_17_deterministic_idempotent_runs`: PASSED (idempotent updates verified)
- `test_18_transaction_rollback_integrity`: PASSED (atomic rollback leaves table intact)
- `test_19_attraction_seasonality_service_lookup`: PASSED (Attraction 1 lookup verified)
- `test_20_raw_climate_data_preservation`: PASSED (165,828 raw records intact)
- `test_21_unrelated_weather_tables_preserved`: PASSED (operational weather tables untouched)
- `test_22_boundary_and_scope_audit`: PASSED (no Qdrant writes, no ranking overrides)

**Overall Status**: 22/22 PASSED (0 FAILED).

---

### 8. Reproducibility & Service Interface

To reproduce the pipeline or execute lookups:

```bash
# 1. Apply database migrations
docker exec wandaraya-api-cutover alembic upgrade head

# 2. Build monthly climate knowledge base (aggregates, climatology, features)
docker exec wandaraya-api-cutover python -m scripts.build_stage12_4c_monthly_climate

# 3. Execute the full test suite
docker exec wandaraya-api-cutover python -m scripts.run_stage12_4c_tests
```

#### Attraction Lookup Example (Python):
```python
from app.database import AsyncSessionLocal
from app.climate.services.attraction_seasonality import AttractionSeasonalityService

async with AsyncSessionLocal() as session:
    service = AttractionSeasonalityService(session)
    # Lookup climate context for Galle Dutch Fort (ID 1) in January (Month 1)
    result = await service.get_attraction_monthly_climate(attraction_id=1, month=1)
    print(result["attraction"]["name"])                 # Galle Dutch Fort
    print(result["climatology"]["rainfall_median_mm"])   # 92.4 mm
    print(result["seasonality_features"]["baseline_a_rainfall_rank"]) # Rank 1 (driest month)
```

---

### 9. Stage 12.4D Readiness
Stage 12.4C is complete and verified:
`MONTHLY_CLIMATE_KNOWLEDGE_BASE_PERSISTED_VERIFIED`

Ready to proceed to **Stage 12.4D — Attraction-Aware Explainable Seasonality Feature Engine**, which will connect these district monthly climate profiles with specific attraction activity profiles (e.g. surfing, hiking, cultural sightseeing).
