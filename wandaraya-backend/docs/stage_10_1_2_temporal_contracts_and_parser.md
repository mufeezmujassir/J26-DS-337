# Stage 10.1.2 — Temporal Data Contracts and Deterministic Opening-Hours Parser

**Status:** COMPLETE_WITH_LIMITATIONS  
**Implementation date:** 2026-10-14  
**Scope:** Typed contracts, a pure Google-weekly-hours normalizer/evaluator,
tests, and read-only pilot validation. No Knowledge Base rows, migrations,
weather components, provider APIs, Airflow DAGs, ranking logic, or dependencies
were changed.

## Research objective

Provide a deterministic, dataset-size-independent foundation for a future
Time-of-Day Context Layer. This work answers only whether a planned local time
is inside a stored **regular weekly** schedule. It does not claim real-time
access, verify temporary closures, infer a visit duration, or assign a final
recommendation rank.

## Implemented architecture

```text
Stored Attraction.opening_hours JSON (read-only)
  -> normalize_google_regular_opening_hours(...)
  -> NormalizedWeeklySchedule + TimingEvidence
  -> evaluate_weekly_schedule(schedule, aware visit datetime)
  -> known_open | known_closed | unknown + reasons
```

The implementation is independent of the existing Semantic–Weather Context
endpoint. It uses canonical attraction IDs and can later join its results to
Stage 10.0.2 envelopes, but it does not modify semantic relevance or weather
suitability.

## Contracts

- `TimeContextRequest`: attraction ID, timezone-aware planned datetime, IANA
  timezone (default `Asia/Colombo`), optional activity identifier and optional
  intended duration.
- `TimingEvidence`: source type/ID/URL, known retrieval/effective dates,
  verification state, freshness state and limitations. Missing facts remain
  null; no timestamp or confidence is invented.
- `NormalizedOpeningInterval`: Google weekday (Sunday=0), local start/end time,
  overnight/always-open type and source reference.
- `NormalizedWeeklySchedule`: normalized intervals, parser version, validation
  status, evidence and warnings.
- `OpeningHoursEvaluation`: local evaluated time, open/closed/unknown state,
  evidence completeness, reason codes and explanation.

## Google weekly-hours semantics and parser rules

The existing connector requests Google `regularOpeningHours`; normalisation
stores `open_now`, `periods`, and `weekday_descriptions`. Google documents a
regular 24-hour schedule as Sunday 00:00 with no close; `open_now` is a current
state and does not answer a future visit question. [Google Place resource](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places)

The parser therefore:

1. Retains Google weekday numbering exactly: Sunday=0 through Saturday=6.
2. Uses `periods` as the calculation input and only retains descriptions as
   display/source material.
3. Accepts same-day intervals where close is strictly later than open.
4. Accepts next-day periods as overnight, including Saturday→Sunday and
   Sunday→Monday.
5. Accepts only the documented single Sunday-00:00/no-close representation as
   all-week always open. Every other missing close is ambiguous.
6. Rejects invalid weekdays/hours/minutes, missing opening points, same-day
   reverse intervals, multi-day spans, overlaps and conflicts.
7. Preserves the input JSON unchanged and returns explicit `missing`,
   `malformed`, `ambiguous`, `unsupported`, or `conflicting` states instead of
   guessing access.

Evaluation converts an aware datetime to the schedule timezone using standard
library `zoneinfo`. Naive datetimes are rejected. The weekly result always
includes `date_exceptions_not_checked`; it does not imply temporary closures,
special days, last-entry rules, or actual access were checked.

## Unknown-state and provenance policy

Missing/JSON-null hours produce `unknown`, not 24/7. Empty schedules are
ambiguous rather than closed. The existing Knowledge Base lacks independently
stored opening-hours provenance and retrieval time, so default Google evidence
includes that limitation and has `freshness_status=not_assessed`. A later source
adapter can preserve Google, official, OpenStreetMap, or manual evidence without
changing these contracts.

## Pilot parser validation

Read-only validation ran on the current pilot snapshot at
`2026-10-14T11:48:22.114563+00:00`.

| Metric | Measured value |
|---|---:|
| Active attractions | 222 |
| Structured schedule objects | 121 |
| Successfully normalised | 120 |
| Missing/JSON-null schedules | 101 |
| Rejected unsupported schedules | 1 |
| Ambiguous schedules | 0 |
| Missing-close source representations | 79 |
| Normalised overnight intervals | 0 |

The one rejected structured record contains a period spanning more than one
day, which this weekly parser deliberately marks unsupported rather than
silently converting. There are 102 schedules not normalised in total when the
101 explicitly missing/JSON-null records are included. The 79 missing-close records match the observed Google
always-open representation and were accepted only when they met the strict
documented shape. Structural normalisation success does not establish factual
accuracy or freshness of the hours.

District 82 is the only observed district with one structured schedule rejected
(14 structured, 13 valid); all other currently structured records normalised.
These values describe the pilot snapshot only and are not national coverage
claims.

## Test methodology and results

No live Google, OpenStreetMap, website, Qdrant, or weather-provider request was
made. Tests use fixed schedule fixtures and timezone-aware datetimes.

```cmd
docker exec -i wandaraya-api python -m pytest tests/time_context/test_google_period_parser.py tests/test_knowledge_base_api.py tests/weather_model/test_weather_context_service.py tests/weather_model/test_attraction_suitability.py tests/recommendation/test_weather_adapter.py tests/recommendation/test_semantic_weather_context_enrichment.py -q
```

Result: **49 passed, 0 failed, 0 skipped**; one third-party deprecation warning.

The temporal suite covers Sunday/Monday numbering, single/multiple/split daily
intervals, opening and closing boundaries, overnight and week-boundary periods,
midnight, regular 24-hour representation, missing closes, JSON null/empty
schedules, invalid points, interval order, overlap conflicts, input immutability,
timezone conversion, naive-datetime rejection, output stability, provenance,
and date-exception non-inference.

Read-only pilot validation is reproducible with:

```cmd
docker exec -it wandaraya-api python -m app.time_context.opening_hours.pilot_validation
```

## Files

- `app/time_context/schemas.py`
- `app/time_context/opening_hours/schemas.py`
- `app/time_context/opening_hours/google_period_parser.py`
- `app/time_context/opening_hours/evaluator.py`
- `app/time_context/opening_hours/pilot_validation.py`
- `tests/time_context/test_google_period_parser.py`
- `data/reports/stage_10_1_2_temporal_parser_validation.json`

## Limitations and research validity

- The 222-attraction dataset is a pilot snapshot, not nationally representative.
- No activity duration is populated; duration must not be inferred.
- No date-specific exceptions, holidays, special days, temporary closure or
  last-entry rule is modeled.
- Existing hour provenance/retrieval time is unavailable; no freshness judgement
  is possible.
- A regular weekly result is provisional operational evidence only, not a safety
  or accessibility determination.
- The parser intentionally supports the verified stored Google shape, not the
  full OpenStreetMap `opening_hours` grammar.

## Exact next-stage recommendation

Stage 10.1.3 should be limited to source acquisition design/implementation with
explicit approval for Google billing, retention and attribution; source
precedence and conflict policy; staleness threshold; and manual-verification
scope. It must store provenance and raw-source references separately from the
existing attraction JSON, remain idempotent, and never overwrite hours without
an explicit validated update policy.
