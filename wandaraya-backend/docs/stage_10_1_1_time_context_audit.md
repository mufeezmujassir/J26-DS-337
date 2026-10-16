# Stage 10.1.1 — Time-of-Day Context Data & Architecture Audit

**Audit date:** 2026-10-14  
**Status:** READY_WITH_GAPS  
**Scope:** Read-only source-code, PostgreSQL, and documentation audit. No
application code, database rows, Qdrant vectors, migrations, API calls, scraping,
Airflow schedules, model artifacts, or approvals were changed.

## 1. Executive summary

The repository has a usable starting point for a Time-of-Day Context Layer:
Google-derived opening-hours JSON, canonical attraction IDs, coordinates,
districts, activity links, source metadata, a Sri Lanka-local weather-date
implementation, and an independent semantic-plus-weather candidate contract.

The observed database has **222 active attractions**. All have coordinates,
district assignment, and Google Place IDs. It has **121 structurally populated
weekly opening-hour objects (54.5%)** and **101 JSON-null opening-hours values
(45.5%)**. Every populated schedule uses the same normalized shape and has
parseable period fields. However, no `AttractionActivity.duration_minutes` value
is populated. Therefore a future time layer can begin with opening-hours hard
constraints for the supported subset, but must return `unknown` rather than
inventing a visit duration or assuming an attraction is open.

This audit does not establish that Google hours are current, that a site is safe
to visit after daylight, or that an attraction is accessible merely because it
has no stated hours.

## 2. Verified repository architecture

| Capability | Verified implementation |
|---|---|
| Attraction hours | `Attraction.opening_hours` is nullable JSON at `app/models/attraction.py:25`. |
| Activity duration | `AttractionActivity.duration_minutes` is nullable integer at `app/models/attraction_activities.py:14`. |
| Location | Nullable attraction `latitude`/`longitude` and `district_id` are at `app/models/attraction.py:14-18`; districts retain centroid latitude/longitude and boundary at `app/models/district.py:6-18`. |
| Activity taxonomy | `activities` plus `attraction_activities`; existing weather aliases are at `app/weather_model/suitability/activity_mapper.py:10-74`. |
| Hours ingestion | Google details requests `regularOpeningHours` and `businessStatus` at `app/knowledge_base/connectors/google_places.py:117-149`; normalisation retains `open_now`, `periods`, and `weekday_descriptions` at `app/knowledge_base/processors/normalizer.py:278-299`. |
| Provenance | Descriptions have source, URL, language, hash, retrieved timestamp at `app/models/attraction_descriptions.py:7-21`. Opening-hours provenance is not independently persisted. |
| Candidate integration | Stage 10.0.2 envelopes preserve identity, coordinates, activity names, source provenance, semantic rank/score at `app/recommendation/context_enrichment/schemas.py:34-62`; orchestration is `SemanticWeatherContextEnrichmentService` at `app/recommendation/context_enrichment/service.py:50-143`. |
| Weather independence | `WeatherContextDimension` is an independent 0–1 contract at `app/recommendation/context_dimensions/weather_context_contract.py:17-46`. |
| Local date precedent | `LiveWeatherClient` converts provider timestamps through `ZoneInfo("Asia/Colombo")` at `app/weather_model/context/live_weather_client.py:95-103`. |
| Router pattern | FastAPI routers are registered in `app/main.py:40,148-155`; Stage 10.0.2 uses a typed POST router. |
| Sessions/migrations | Async SQLAlchemy session dependency is `app/database.py:7-23`. Alembic is listed in requirements, but no timing-specific migration exists. |
| Scheduling/connectors | Google Places connector, KB ingestion/refresh services, and tourism/weather Airflow DAGs exist. No time-context DAG or connector exists. |

`opening_hours` is exposed in the attraction model but is not part of the
existing public Knowledge Base summary/detail schemas. The future layer should
read it from a dedicated read-only repository, not alter current KB endpoints.

## 3. Read-only PostgreSQL coverage findings

The following counts were collected in a `SET TRANSACTION READ ONLY` transaction
on 2026-10-14.

| Finding | Count | Interpretation |
|---|---:|---|
| Active attractions | 222 | Measured current dataset snapshot. |
| Coordinate pairs | 222 | 100%; usable for local daylight calculations. |
| Valid district IDs | 222 | 100%; no district substitution needed for current data. |
| Google Place IDs | 222 | 100%; possible future source refresh identifier. |
| SQL non-null `opening_hours` | 222 | This overstates timing coverage because JSON `null` is stored instead of SQL NULL. |
| Structured opening-hour object | 121 | 54.5%; candidate for strict parser validation. |
| JSON `null` opening-hours value | 101 | 45.5%; must remain unknown. |
| Empty `{}` object / string | 0 | No empty structured object observed. |
| Objects with non-empty `periods` array | 121 | Structurally parseable weekly schedule candidates. |
| Activity-linked attractions | 146 | 65.8%; 76 active attractions have no activity link. |
| Activity links with a duration | 0 | No measured duration distribution exists. |
| Duplicate attraction/activity pairs | 0 | Association uniqueness is consistent in the audited data. |

### Observed opening-hours format

All 121 populated values are JSON objects with exactly these top-level keys:

```json
{
  "open_now": true,
  "periods": [
    {"open": {"day": 0, "hour": 5, "minute": 30},
     "close": {"day": 0, "hour": 20, "minute": 0}}
  ],
  "weekday_descriptions": ["Monday: 5:30 AM – 8:00 PM"]
}
```

`periods` is always an array. The audit found 380 `open` entries, 301 explicit
`close` entries, no malformed hour/minute/day values, and two cross-day periods.
Missing `close` is consistent with Google’s 24-hour representation, but the
future parser must verify this interpretation per schedule rather than assuming
every missing close means 24/7. Period-count distribution: 79 attractions have
1 period, 1 has 2, 2 have 6, 38 have 7, and 1 has 21. `open_now` is a retrieval-
time observation and must not be used to answer a future-date visit query.

There is no separate record of time-specific source, retrieval timestamp,
effective date, exception, last-entry time, or temporary-closure reason.
`last_sync_at` is present for all active attractions and spans 2026-10-02 to
2026-10-13, but no approved freshness threshold exists; staleness is therefore
**not evaluated**.

Coverage is uneven. For example, structured-hour coverage is 83/106 for Urban
& City Attractions, 44/108 for Culture & Heritage, 15/17 for Religious &
Spiritual, 0/3 for Beaches & Coastal, and 0/3 for Water & Marine Activities.
This is a coverage observation, not evidence that the latter attractions are
always open or unsuitable.

## 4. Source feasibility matrix

| Source | Useful fields/method | Reliability and refresh | Constraints/fallback |
|---|---|---|---|
| Existing KB | Stored `periods`, descriptions, coordinates, Place ID, activities | Reuse immediately; only structured objects enter parser. | No hourly provenance or duration; JSON null becomes unknown. |
| Google Places API (New) | `regularOpeningHours`, `currentOpeningHours`, `businessStatus`, `timeZone`, `utcOffsetMinutes`, optional secondary hours | Place ID refresh, rate-limited and scheduled only after policy design. Current hours cover the next seven days and include exceptional-day information. | These fields have billable SKU tiers; use field masks. Google policy says content caching/storage and attribution requirements apply, while Place ID is an explicit cache exception. Confirm current terms/billing before implementation. [Google fields](https://developers.google.com/maps/documentation/places/web-service/data-fields.md), [Place resource](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places), [policy](https://developers.google.com/maps/documentation/places/web-service/policies) |
| Official operator sites | Published visiting hours, closures, ticket/last-entry notices | Best source for archaeological sites, museums, parks, religious sites and managed recreation; refresh by source class or official-change notice. | Static HTML, JSON-LD, downloadable schedule, authorized rendered page, or manual verification are possible. No website was fetched; robots, terms, licences, and source-specific access require verification. Failure remains unknown. |
| OpenStreetMap / Overpass | `opening_hours`, `opening_hours:url`, `source:opening_hours`, `check_date:opening_hours` | Supplemental only; preserve OSM object/version and check date. | Syntax supports complex weekly/date/sunrise rules and needs a standards-capable parser. OSM data quality is volunteer-maintained and must not override higher-trust official evidence automatically. Attribute and comply with ODbL. [OSM opening-hours tag](https://wiki.openstreetmap.org/wiki/Key%3Aopening_hours), [source metadata](https://wiki.openstreetmap.org/wiki/Key%3Asource%3Aopening_hours) |
| Astronomical calculation | Coordinates, Sri Lanka local date, IANA timezone | Deterministic at request time; no external provider required once a vetted library is adopted. | `astral` is not currently installed. Python `zoneinfo` already exists in the standard library and is used by weather. Daylight is a soft context signal, not a safety, access, or opening proof. [Astral](https://astral.readthedocs.io/en/latest/), [zoneinfo](https://docs.python.org/3/library/zoneinfo.html) |

## 5. Temporal requirements and future normalisation design

Hard constraints must be distinct from preferences:

- **Hard:** explicit temporary/permanent closure, explicitly closed weekly/date
  interval, or a visit whose stated duration cannot fit before a known closing
  time. Unknown schedule is not a hard closure.
- **Soft:** activity prefers daylight, sunrise/sunset proximity, user-preferred
  time band, or adequate (but not verified) remaining visit time.

Stage 10.1.2 should introduce only versioned, source-aware contracts—not a
migration until evidence fields and retention policy are approved. Normalised
records should retain raw source payload reference/hash, source type, source URL
where applicable, retrieved time, effective interval/date, timezone, parser
version, confidence, and conflict status. Required semantics include weekly
multiple intervals, overnight periods, 24-hour periods, specific-date
exceptions, open-ended intervals, closures, and last-entry as a **separate
optional fact**. Never derive last entry from closing time without an explicit
policy.

Use `Asia/Colombo` and an aware planned local visit datetime. Python `zoneinfo`
is sufficient for this location/date conversion; coordinate-based astronomy can
be added later through a reviewed dependency such as Astral.

## 6. Proposed future Time Context contract

This is a design proposal, not implemented code:

```text
TimeContextRequest
  attraction_id, planned_visit_at_local, requested_activity_id/name?,
  optional_visit_duration_minutes, timezone="Asia/Colombo"

TimeContextDimension
  attraction_id, dimension="time_of_day", available,
  hard_constraint_status = open | closed | unknown | conflict,
  soft_suitability_score = 0..1 | null,
  level, evidence_reliability, source_provenance[],
  schedule_effective_at, daylight_window?,
  explanations[], rule_version
```

`soft_suitability_score` must be independent of semantic similarity and weather
suitability. `null` means unknown; it must never become zero. Candidate identity
continues to use canonical integer `Attraction.id` from Stage 10.0.2.

## 7. Research validity, uncertainty and evaluation

The layer must preserve source provenance, retrieved timestamps, effective
dates, source freshness, parser/rule version, verified/unverified status and
conflict details. It should report, not conceal, missing schedules. Key bias
risks are stronger coverage for popular/urban attractions, sparse rural/natural
hours, differing refresh cycles, inconsistent third-party records, and the
difference between managed venues and public outdoor sites.

Future measured evaluation metrics should include schedule coverage, parser
success/failure rate by source, unknown rate, source-conflict rate, hard-
constraint precision/recall against manually verified cases, expert agreement,
candidate-to-context mapping accuracy, and latency. None has been measured in
this audit.

## 8. Prioritised implementation plan

| Stage | Purpose and deliverable | Dependencies and acceptance criteria |
|---|---|---|
| 10.1.2 | Typed schemas and schedule normalisation parser. | Pydantic, `zoneinfo`; tests for multiple intervals, 24/7, overnight, malformed and unknown inputs. No DB changes. |
| 10.1.3 | Source-acquisition policy and source adapters. | Approved Google billing/retention policy, official-site permissions, OSM attribution. Dry-run only; provenance and retry tests. |
| 10.1.4 | Operating-hours engine. | Normalised schedules; deterministic open/closed/unknown tests, date exception and time-zone tests. |
| 10.1.5 | Daylight engine. | Reviewed astronomy dependency or equivalent; coordinate/date regression fixtures; return unknown with missing coordinates. |
| 10.1.6 | Activity timing rules. | Expert-reviewed rule table and versioning; duration remains optional; no invented duration/last entry. |
| 10.1.7 | Independent Time Context contract and API. | Engines above; typed explainable output, null unknowns, no final rank. |
| 10.1.8 | Candidate integration with Stage 10.0.2. | Canonical IDs and batched hydration; semantic/weather scores unchanged; no N+1 query regression. |
| 10.1.9 | Research validation. | Manually verified benchmark set; report coverage, agreement, errors and bias by attraction class. |
| 10.1.10 | Approved automation. | Source policies, rate limits, idempotency, provenance, monitoring and human review; no automatic truth overwrite. |

## 9. Risks, unresolved questions and readiness

**Critical gaps:** 45.5% of attractions lack structured hours, all duration
fields are empty, current storage lacks hour-specific provenance/exception
history, and external source terms/billing must be approved before collection.

**Decisions required before Stage 10.1.3:** approved source precedence and
conflict policy; Google billing/retention/attribution review; whether manual
verified records are in scope; operational definition of staleness; and which
activities require an explicit duration before a closing-time hard constraint
can be issued.

**Readiness for Stage 10.1.2:** **READY_WITH_GAPS.** Schema/parser work can
safely begin because structured schedule examples and local-time precedent are
available. Acquisition, operational evaluation, and hard visit-fit decisions
must remain blocked until the listed evidence and policy decisions are made.
