# Stage 10.1.3B (Gate 1) — Controlled Timing Source Acquisition Connectors

**Status:** COMPLETE_WITH_LIMITATIONS — offline implementation only.

## Verified integration

Gate 1 reuses the existing Google Places connector identity (`google_place_id`),
the normalizer’s `regularOpeningHours` transformation, the strict Stage 10.1.2
weekly parser, and the Stage 10.1.3A policy/reconciliation contracts. It adds
no provider client, API key handling, database model, migration, Airflow DAG,
recommendation change, or Qdrant write.

## Source adapters

- **Google Places:** builds only a future request plan with the minimum timing
  field scope: `id`, `regularOpeningHours`, `currentOpeningHours`, and
  `businessStatus`. It validates fixture identity against the requested Place
  ID. `currentOpeningHours` and `openNow` are retained only as provider metadata
  and are never treated as an arbitrary future-date fact.
- **Official operator:** accepts only explicit HTTPS allowlisted URLs with
  documented robots/access permission. It supports fixture-only simple JSON-LD
  `openingHoursSpecification`; free text, arbitrary HTML, CAPTCHA/auth flows,
  and generic crawling are outside this gate.
- **OpenStreetMap:** preserves element ID, ODbL/attribution reference and raw
  `opening_hours` evidence. It deliberately marks grammar as unsupported until
  an approved compliant parser and license review exist.

## Gates and pipeline

The reusable offline assessment performs:

```text
adapter fixture validation -> identity validation -> provenance -> normalisation
-> governance reconciliation -> review classification -> persistence assessment
```

It defaults to deny: a policy must be approved, the source must permit fetch,
Google’s field/billing scope must be expressly allowed, and retention remains
separate from fetch. Gate 1 always returns `persistence_eligible=false`; it
never overwrites `Attraction.opening_hours` or resolves conflicts automatically.

## Pilot manifest

The 12-entry manifest at `data/reports/stage_10_1_3b_pilot_manifest.json` is a
read-only pilot snapshot selected for district/category/hours-state diversity.
It uses a declared fixed seed and has `not_authorised_for_fetch_or_persistence`
status for every entry. It is not evidence of national representativeness.

## Offline validation

```cmd
docker exec -i wandaraya-api python -m pytest tests/time_context/test_gate1_timing_adapters.py tests/time_context/test_source_governance.py tests/time_context/test_google_period_parser.py -q
```

The focused Gate 1/parser/governance suite completed with **60 passed, 0 failed,
0 skipped**. The broader Knowledge Base, weather, and recommendation regression
suite completed with **82 passed, 0 failed, 0 skipped** (one third-party
deprecation warning). Tests use fixtures only: no Google,
official site, OSM/Overpass, database, or Qdrant call is made.

## Gate 2 prerequisites

Before a controlled live pilot, approve per-source terms, Google billing field
scope and attribution/retention terms, official domains/URLs/robots/access
permission, OSM license/parser choice, freshness threshold, manual-review
workflow, rate limits/timeouts, and the exact pilot manifest. Gate 2 must run a
small monitored sample and report actual source outcomes separately from this
offline validation.
