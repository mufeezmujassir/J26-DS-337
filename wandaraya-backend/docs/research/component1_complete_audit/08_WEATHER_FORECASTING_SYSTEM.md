# Weather Forecasting System

The system uses multiple weather evidence types, not one universal predictor:

- 0-5 days: OpenWeatherMap live/API forecast, daily interpretation from available 3-hour intervals.
- 6-90 days: a production-approved monthly model run is required.
- Beyond 90 days: historical monthly climatology, explicitly not a date-specific forecast.
- Past dates: historical observations.

Evidence: `app/weather_model/context/source_selector.py:8-49` (A).

Prophet is implemented for monthly targets with linear growth, yearly seasonality, no weekly/daily seasonality, additive mode, `changepoint_prior_scale=0.05`, `seasonality_prior_scale=10`, interval width 0.80, and a minimum 24 observed months. Negative rainfall predictions are clipped to zero (`forecasting/prophet_trainer.py`). The Stage 12.4A audit found 20 Prophet runs (7 validated), 18 monthly-climatology runs (8 validated), and 5 seasonal-naive runs (1 validated), all with zero production-approved runs and three-month registry horizons. Therefore the medium-term production path may be unavailable. No Component 1 LSTM implementation was found.

Rule-based suitability evaluates activity thresholds. Temperature outside a configured range incurs a bounded penalty up to 0.45; daily/interval rainfall incurs a bounded penalty up to 0.60 using rainfall/40; calendar-month rainfall is informational and is not misused as daily rainfall. Exact activity profiles live in `app/weather_model/context_scoring/activity_weather_rules.py` and suitability modules. These are engineering heuristics, not validated physiological models.

Key limitations: weather provider uncertainty, district-to-attraction spatial mismatch, aggregation of intervals, absence of an approved monthly forecast, and climatology not representing a particular future day. Provenance and resolution must be shown with every score.

Suggested tests: a near-term dry beach request, a rainy hiking request, a 30-day request without an approved run, a 180-day request returning climatology, and a provider failure. Never present the climatology output as a guaranteed forecast.

