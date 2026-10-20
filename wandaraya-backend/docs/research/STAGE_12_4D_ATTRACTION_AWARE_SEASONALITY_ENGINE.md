# WANDARAYA Research Documentation: Stage 12.4D
## Attraction-Aware Explainable Seasonality Feature Engine

### 1. Executive Summary & Research Objectives
As part of the **WANDARAYA — Multi-Agentic AI for Sustainable Tourism in Sri Lanka** research initiative (Component 1: Context-Aware Recommendation and Orchestration Agent), Stage 12.4D designs, implements, validates, and persists the **Attraction-Aware Explainable Seasonality Feature Engine**.

Prior stages established the 16-year daily historical climate foundation (Stage 12.4B) and the 25-district macroclimate monthly climatology (Stage 12.4C). However, district-level climate baselines are insufficient for fine-grained tourist decision-making:
1. **Activity Asymmetry**: A calendar month that is suboptimal for beach tourism (e.g., high wave energy, frequent rain) may be ideal for inland wildlife viewing, tea plantation visits, or cultural exploration.
2. **Attraction-Specific Context**: Sri Lanka possesses over 6,000 diverse tourist attractions spanning coastlines, montane cloud forests, and arid scrublands. Tourists do not travel to an abstract district; they engage in specific activities at specific attractions.
3. **Safety and Partial Evidence**: Predicting travel suitability purely from historical rainfall can be dangerous if applied naively to marine sports (requiring ocean swell/current data) or waterfall bathing (requiring flash-flood and river discharge metrics).

Stage 12.4D bridges this gap by mapping each attraction to a deterministic, research-backed **16-activity taxonomy**, calculating multi-variable climate suitability scores S_climate(a,k,m), generating natural-language explainability rationales, enforcing strict **abstention and safety policies**, and persisting all 121,524 attraction-activity-month profiles to PostgreSQL with full transaction integrity.

---

### 2. Research Hypothesis & Mathematical Formulation

#### 2.1 The Novelty Hypothesis
> **Hypothesis**: Decoupling seasonal tourism favorability into multi-variable, activity-conditioned suitability scores yields significantly higher behavioral differentiation, avoids catastrophic over-generalization of monsoon seasonality, and enables truthful natural-language explainability with explicit uncertainty bounds.

#### 2.2 Mathematical Formulation of Climate Suitability
For an attraction a, activity type k, and calendar month m in {1, ..., 12}, the composite climate suitability score S_climate(a,k,m) in [0, 1] is formulated as a linear combination of normalized physical climatological sub-indices:

S_climate(a,k,m) = w_rain * I_rain(a,k,m) + w_rel * I_rel(a,k,m) + w_temp * I_temp(a,k,m) + w_hum * I_hum(a,k,m) + w_solar * I_solar(a,k,m) + w_wind * I_wind(a,k,m)

Subject to: sum(w_j) = 1.0, w_j >= 0.

#### 2.3 Component Sub-Indices
1. **Relative Rainfall Favorability (I_rain)**:
   Penalizes months exceeding the activity-specific wet-season rainfall threshold R_crit:
   I_rain(a,k,m) = max(0.0, 1.0 - R_mean(a,m) / R_crit(k))

2. **Rainfall Reliability Index (I_rel)**:
   Rewards interannual consistency and penalizes erratic monsoon volatility using the coefficient of variation (CV = std / mean):
   I_rel(a,k,m) = 1.0 / (1.0 + min(CV(a,m), 2.5))

3. **Temperature Comfort Index (I_temp)**:
   Gaussian-decay function centered at the activity ideal temperature T_opt(k) with tolerance spread sigma_T(k):
   I_temp(a,k,m) = exp(- (T_mean(a,m) - T_opt(k))^2 / (2 * sigma_T(k)^2))

4. **Humidity Comfort Index (I_hum)**:
   Penalizes relative humidity when it deviates from the activity comfort band [H_min, H_max]:
   I_hum(a,k,m) = 1.0 - max(0, H_min - H_mean, H_mean - H_max) / 100.0

5. **Solar & Wind Comfort Indices (I_solar, I_wind)**:
   Normalized indices scaling clear-sky solar irradiance and safe wind speed thresholds according to activity requirements.

#### 2.4 Relative Annual Ranking and Classification
Within each (a, k) pair, the 12 calendar months are ranked by S_climate:
- **Rank 1**: Most favorable month; **Rank 12**: Least favorable month.
- **Suitability Classes**:
  - IDEAL: S_climate >= 0.75
  - FAVORABLE: 0.60 <= S_climate < 0.75
  - MODERATE: 0.45 <= S_climate < 0.60
  - UNFAVORABLE: S_climate < 0.45

---

### 3. Hierarchical Activity Taxonomy & Profiles

Sixteen (16) standardized activity profiles were engineered across 5 parent categories:

| Activity Code | Activity Name | Parent Category | Primary Climate Drivers | Evidence Category | Missing Evidence Requirements |
|---|---|---|---|---|---|
| beach_coastal_relaxation | Beach & Coastal Relaxation | Coastal & Marine | Rain, Solar, Wind | SUPPORTED_CLIMATE_ONLY | None |
| surfing_water_sports | Surfing & Water Sports | Coastal & Marine | Wind, Rain, Swell | CLIMATE_ONLY_PARTIAL | Ocean swell, wave height, bathymetry |
| snorkeling_diving | Snorkeling & Scuba Diving | Coastal & Marine | Rain, Wind, Turbidity | CLIMATE_ONLY_PARTIAL | Underwater visibility, water turbidity |
| scenic_coastal_walk | Scenic Coastal Walking | Coastal & Marine | Rain, Wind, Temp | SUPPORTED_CLIMATE_ONLY | None |
| hiking_trekking | Hiking & Mountain Trekking | Nature & Adventure | Rain, Temp, Wind | SUPPORTED_CLIMATE_ONLY | None |
| wildlife_safari | Wildlife Safari & Game Drives | Nature & Adventure | Rain, Temp, Grassland | CLIMATE_ONLY_PARTIAL | Animal migration, park closure dates |
| birdwatching | Birdwatching & Eco-Tours | Nature & Adventure | Rain, Solar, Wind | SUPPORTED_CLIMATE_ONLY | None |
| waterfall_visit_bathing | Waterfall Excursions | Nature & Adventure | Rain, Flood Risk | CLIMATE_ONLY_PARTIAL | River discharge, flash flood safety |
| tea_plantation_agritourism | Tea Plantation Agritourism | Nature & Adventure | Temp, Rain, Solar | SUPPORTED_CLIMATE_ONLY | None |
| cultural_sightseeing | Cultural & Heritage Touring | Cultural & Heritage | Rain, Temp, Hum | SUPPORTED_CLIMATE_ONLY | None |
| religious_pilgrimage | Religious Pilgrimage | Cultural & Heritage | Rain, Temp, Crowds | CLIMATE_ONLY_PARTIAL | Festival calendar, Poya crowding |
| archaeological_exploration | Archaeological Exploration | Cultural & Heritage | Temp, Rain, Solar | SUPPORTED_CLIMATE_ONLY | None |
| urban_shopping_dining | Urban Dining & Shopping | Urban & Wellness | Rain, Temp, Hum | SUPPORTED_CLIMATE_ONLY | None |
| ayurveda_wellness_retreat | Ayurveda & Wellness Retreat | Urban & Wellness | Temp, Hum, Rain | SUPPORTED_CLIMATE_ONLY | None |
| photography_landscape | Landscape Photography | Specialized | Solar, Rain, Cloud | SUPPORTED_CLIMATE_ONLY | None |
| scenic_railway_journey | Scenic Railway Journey | Specialized | Rain, Fog, Solar | SUPPORTED_CLIMATE_ONLY | None |

---

### 4. Attraction Inventory & Geographic Resolution Findings

#### 4.1 Attraction Coverage Statistics
- Total active attractions in PostgreSQL: 6,120.
- Attractions mapped to >= 1 activity: 4,472 (73.07%).
- Unique Attraction-Activity Mapping Pairs: 10,127.
- Unmapped/Unclassified attractions: 1,648 (26.93%) - strictly categorized as UNSUPPORTED_UNCLASSIFIED without fabrication.
- Total Monthly Feature Profiles Generated: 10,127 pairs x 12 months = 121,524 rows.

#### 4.2 NASA POWER Spatial Coarseness & Empirical Resolution Reconciliation
A key research contribution of Stage 12.4D was the empirical resolution of the spatial discretization characteristics of NASA POWER (MERRA-2 / GEOS):
- NASA POWER delivers meteorological products on a 0.5 deg x 0.5 deg latitude/longitude grid (~55 km x 55 km).
- **Horton Plains vs Nuwara Eliya Centroid**:
  - Horton Plains: (6.809 N, 80.802 E), Elevation: 2,134 m MSL.
  - Nuwara Eliya District Centroid: (7.013 N, 80.757 E), Elevation: 1,868 m MSL.
  - Empirical Finding: Both coordinates fall within the exact same MERRA-2 0.5 deg grid box. NASA POWER reports an identical model elevation of 681.44 m and yields identical timeseries (mean temperature difference = 0.00 deg C).
  - Research Implication: Reanalysis-derived datasets cannot resolve fine-scale montane lapse rates without downscaling. The system explicitly logs GEOGRAPHIC_SOURCE_TYPE: ATTRACTION_COORDINATE_REANALYSIS for Horton Plains, Galle Fort, and Anuradhapura, but notes the grid limitation in the evidence rationale.
- **District Proxy vs Dedicated Attraction Resolution**:
  - 3 dedicated coordinate locations: Galle Dutch Fort (Attraction 1), Anuradhapura (Attraction 16), Horton Plains (Attraction 24) utilize their own 36 dedicated climatology records (climate_attraction_monthly_climatology).
  - Remaining 6,117 attractions utilize authoritative district climatology (climate_district_monthly_climatology) linked via climate_attractions.district_id.

---

### 5. PostgreSQL Schema Architecture (Migration c90d1e2f3a4b)

Six relational tables were designed and deployed:
1. climate_activity_types (16 rows)
2. climate_activity_profiles (16 rows)
3. climate_attraction_activity_mappings (10,127 rows)
4. climate_attraction_monthly_climatology (36 rows)
5. climate_attraction_activity_seasonality (121,524 rows)
6. climate_activity_processing_runs (1 row)

---

### 6. Research Experiments & Empirical Validation

#### 6.1 Experiment 1: Activity Differentiation within Identical Geography
- **Galle Dutch Fort (Attraction 1)**:
  - Cultural Sightseeing: Top months Jan (Rank 1, 0.831), Feb (Rank 2), Mar (Rank 3). Bottom months Nov (Rank 12, 0.356), May (Rank 11).
  - Surfing: Peaks during South coast surf season (Dec-Mar); severely downgraded during the Southwest monsoon (May-Sep) due to high precipitation and onshore winds.
- **Horton Plains (Attraction 24)**:
  - Hiking & Trekking: Top months July (Rank 1, 0.806), Mar (Rank 2), Jun (Rank 3). Bottom months Nov (Rank 12, 0.349), Oct (Rank 11).
  - Cultural Sightseeing: Top months Mar (Rank 1, 0.793), Feb (Rank 2), Jul (Rank 3).

#### 6.2 Experiment 2: Geographic Sensitivity Across Microclimates
- **Regional Contrast**:
  - Southwestern Coast (Galle): Unfavorable in May and Oct/Nov (Inter-monsoon / SW Monsoon). Peak Jan-Feb.
  - Eastern Coast (Batticaloa): Favorable June-August (dry inter-monsoon season). Unfavorable in Nov-Dec (Northeast Monsoon).
  - This reproduces the classic Sri Lankan dual-monsoon beach complementarity, validating macroclimatic realism.

#### 6.3 Experiment 3: Baseline Comparison (Spearman Rank Correlation)
- Baseline A (Rainfall-only): Spearman rho = 0.958.
- Baseline B (Multivariable Comfort): Spearman rho = 0.986.
- Baseline C (Variability-Aware Risk): Spearman rho = 0.881.

#### 6.4 Experiment 4: Feature Ablation Analysis
- Relative Rainfall Favorability: Ablated rho = 0.217, Mean Rank Shift = 3.33 ranks. **Impact: CRITICAL**.
- Temperature Comfort Index: Ablated rho = 0.979, Mean Rank Shift = 0.50 ranks. **Impact: MODERATE**.
- Humidity Comfort Index: Ablated rho = 0.972, Mean Rank Shift = 0.50 ranks. **Impact: MODERATE**.
- Rainfall Reliability Index: Ablated rho = 0.993, Mean Rank Shift = 0.17 ranks. **Impact: MODERATE**.

#### 6.5 Experiment 5: Weight Sensitivity & Stability
Perturbing activity weights by +/- 20% resulted in mean Spearman rank correlation > 0.96 across all 16 activities.

#### 6.6 Experiment 6: Uncertainty Propagation & Abstention Integrity
- Supported Climate Only: 101,196 profiles (83.27%).
- Climate Only Partial (Abstention Enforced): 20,328 profiles (16.73%).
- Uncertainty score bounds: Range [0.267, 0.760], Mean 0.447.

---

### 7. Test Suite & Quality Assurance
- **Stage 12.4D Test Suite**: **30 / 30 PASSED** (scripts/run_stage12_4d_tests.py).
- **Stage 12.4C Regression Suite**: **22 / 22 PASSED** (scripts/run_stage12_4c_tests.py).

---

### 8. Reproducibility & Execution Commands
`ash
docker exec -i wandaraya-api-cutover alembic upgrade c90d1e2f3a4b
docker exec -i wandaraya-api-cutover python scripts/build_stage12_4d_attraction_seasonality.py
docker exec -i wandaraya-api-cutover python scripts/run_stage12_4d_tests.py
docker exec -i wandaraya-api-cutover python scripts/run_stage12_4c_tests.py
`
