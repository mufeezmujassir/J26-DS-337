# Component 1 figures and interpretation

## Figure 1 — Active attractions by tourism theme

The verified catalogue contains **1,056 active attractions**. It is dominated by **Heritage** attractions (324 mappings), followed by **Scenic** (318 mappings). Because attractions may carry more than one theme, these bars are category mappings rather than mutually exclusive record counts. The imbalance supports combining semantic similarity with explicit theme constraints during recommendation.

## Figure 2 — Geographic coverage

The expanded catalogue is geographically imbalanced. **Ampara** contains the largest number of verified records (77), while 0 districts contain no active attraction. The chart represents database coverage, not the true physical supply of tourism attractions. Candidate diversity will therefore vary by district.

## Figure 3 — Data completeness

The chart measures the availability of recommendation-critical metadata across all **1,056 active attractions**. Description and district coverage should remain at 100%, while optional Google fields such as ratings, websites, and opening hours naturally have lower coverage. The system must treat missing optional values as unavailable evidence rather than inventing them.

## Figure 4 — Source verification outcomes

Of **1,163 complete DayOuting source records**, **945 (81.3%)** were either promoted as verified new attractions or linked to an existing attraction. Remaining records are isolated in review states instead of being exposed to users. This is the main data-quality safeguard against junctions, locality names, duplicates, and ambiguous category assignments.

## Figure 5 — Attraction feature correlation heatmap

The strongest non-diagonal relationship is between **Description length** and **Image count** (r = **0.72**). Correlation describes association, not causation. Binary fields such as website and opening-hours availability are included as 0/1 indicators, while review count is log-transformed to reduce extreme skew.

## Figure 6 — Rating versus review volume

The scatter plot separates popularity (review volume) from satisfaction (rating). Review count uses a logarithmic axis because a small number of famous attractions have orders of magnitude more reviews. Colour represents log-transformed description length, allowing content richness to be inspected without implying that it causes higher ratings.

## Figure 7 — Daily Prophet test performance

Temperature is substantially more predictable than rainfall. On the untouched 2025 test set, minimum temperature achieved a mean MAE of **0.905°C**, while maximum temperature achieved **1.397°C**. Rainfall achieved a mean MAE of **5.537 mm/day** and RMSE of **13.763 mm/day**. The larger rainfall RMSE indicates that high-rainfall events produce much larger errors than ordinary days. Long-range rainfall forecasts should therefore be displayed with uncertainty and used as suitability evidence rather than guaranteed exact weather.

## Figure 8 — Rain-event classification

Across 25 districts, mean rain-event precision was **0.851**, recall was **0.579**, F1-score was **0.678**, and accuracy was **0.623**. Precision being higher than recall means that predicted rainy days are usually credible, but some actual rainy days remain undetected. This supports conservative explanations and indoor alternatives when rainfall risk is uncertain.

## Figure 9 — Galle historical seasonality

The Galle profile shows clear month-to-month variation. **February** has the highest multi-variable suitability score (0.840), while **November** has the highest historical mean rainfall (398.92 mm/month). Temperature comfort remains relatively stable, so rainfall and humidity explain most of the seasonal movement. This profile represents historical climatology and must not replace a live or date-specific daily forecast.

## Figure 10 — Chronological modelling split

The chronological split prevents future information from leaking into model training. Observations from 2010–2023 are used for fitting, 2024 is used for threshold selection and validation, and 2025 remains untouched until final evaluation. This produces a more realistic estimate of future forecasting performance than a random train-test split.

## Suggested placement in the report

- Place Figures 1–6 under **Attraction Dataset — Key Insights and Data Quality**.
- Place Figure 10 under **Feature Extraction / Model Preparation**.
- Place Figures 7 and 8 under **Weather Forecasting — Modelling and Results**.
- Place Figure 9 under **Historical Seasonality — Key Insights**.
