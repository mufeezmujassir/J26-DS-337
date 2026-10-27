# Holiday, Poya and Event Context

The layer joins date-aware holiday records, Poya classification, verified tourism events, attraction links and requested interests. Poya matters in Sri Lanka because religious/cultural relevance and operating constraints may differ, but the code does not assume every holiday improves every attraction.

The experimental weighted score uses holiday 0.20, Poya 0.35, verified event 0.25 and interests 0.20. Missing features are excluded and remaining eligible weights are renormalized. The configuration explicitly says the weights are heuristic, statistically unoptimized and not used by production ranking (`config/holiday_event_scoring.yaml:1-12`).

Important safeguards:

- generic holiday eligibility is distinct from Poya to prevent double-counting;
- only verified events are score-eligible;
- Poya evidence does not prove opening status or crowd level;
- no eligible evidence returns null rather than a fabricated neutral score;
- event geography/date and explicit attraction links provide relevance.

At audit runtime the database contained 45 holiday records, one event and five event-attraction links (B). Sparse event coverage limits claims. Calendar ingestion is configured annually; event ingestion daily. Configured schedules do not prove that every run succeeded.

Scenarios: a culturally relevant religious site on Poya may receive Poya relevance; an unrelated attraction receives only eligible generic evidence; an unverified/cancelled/out-of-district/expired event must not provide a verified-event boost; missing dates cannot be matched. Evidence: `app/holiday_event/context_scoring.py`, `app/holiday_event/context_features.py`, adapters and source connectors (A).

