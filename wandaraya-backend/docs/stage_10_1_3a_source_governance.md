# Stage 10.1.3A — Timing Source Governance, Provenance and Offline Acquisition Framework

**Status:** COMPLETE — OFFLINE GOVERNANCE ONLY  
**Implementation date:** 2026-10-14

## Scope and safety boundary

This stage adds typed, pure-Python contracts for a future timing-source workflow.
It performs no HTTP request, scrape, connector execution, database migration,
database write, Airflow action, Qdrant action, or update to `Attraction` data.
It does not claim that any source is current or authoritative.

The Stage 10.1.2 pilot remains the factual basis: 222 active attractions, 121
structured schedules, 120 valid parser outputs, 101 missing schedules and one
unsupported schedule. The 79 records with an absent Google close point were
accepted only where they matched the strict single Sunday 00:00 documented
always-open representation; all other missing-close shapes remain ambiguous.

## Implemented contracts

`app/time_context/governance/schemas.py` separates three kinds of information:

- `TimingSourceFacts`: canonical attraction ID, source identity/URL/reference,
  evidence type, retrieval/effective dates, timezone, supported source-specific
  indicators, and retention metadata.
- `ResearcherAnnotation`: review state and attributable notes; these are not
  source facts.
- `SystemDerivedMetadata`: parser version, extraction warnings and freshness
  assessment; these are not presented as source claims.

Supported source types are `existing_knowledge_base`, `google_places`,
`official_operator`, `openstreetmap`, `manual_verification`, and `unknown`.
No confidence score is invented. Missing source data stays null/unknown.

## Governance and reconciliation policy

`TimingGovernancePolicy` is unapproved by default. It records explicit,
reviewable source rules instead of a universal numeric trust ranking: retention
permission, refresh eligibility, verification requirement, permitted exception
override, and an optional freshness threshold. Without an approved policy the
result is `policy_unresolved`.

`reconcile_timing_evidence(...)` is pure and accepts at least two evidence
records. It returns one of `consistent`, `conflicting`, `insufficient_evidence`,
`review_required`, or `policy_unresolved` with stable reason codes. It checks
canonical identity, provenance, retention, freshness, normalised schedule
availability, effective dates, direct schedule agreement and disagreement.

A date-specific exception can be selected only when all of these are true:

1. the policy is approved;
2. its source rule expressly permits a verified exception override;
3. the exception is applicable to the requested date; and
4. the evidence meets the configured verification status.

Otherwise no source wins automatically. Conflicting schedules remain
`conflicting`; incomplete, stale, retention-unknown, or provenance-incomplete
evidence requires review.

## Future connector protocol

`acquisition.py` supplies a planning-only `FutureTimingConnector` protocol and
`AcquisitionPlan`. The specified future sequence is:

```text
discover -> fetch -> extract -> validate -> normalise -> reconcile -> review -> persist
```

Each future connector must separately prove source access permission, terms,
attribution, field scope, rate-limit settings, retention eligibility, extraction
validity, and persistence approval. A policy authorises neither fetch nor
persistence by default. This module contains no implementation for Google,
official operators, or OpenStreetMap.

## Pilot sampling design

`sampling.py` defines deterministic, seed-based offline stratification. It can
stratify an explicitly provided candidate list by district, category,
managed/natural status, hours status, source status, and a supplied settlement
context. Unknown values are retained. It is a reproducible pilot-sampling
method, not a national-representativeness claim and does not query PostgreSQL.

## Validation coverage

Synthetic tests cover source facts versus derived annotations, canonical-ID
matching, policy unresolved, source agreement/disagreement, insufficient
evidence, missing provenance, unknown/stale freshness, retention statuses,
unsupported schedules, verified/unverified and applicable/non-applicable date
exceptions, no automatic winner, acquisition policy isolation, deterministic
sampling, input immutability, and Stage 10.1.2 parser compatibility.

The focused governance/parser command completed with **51 passed, 0 failed,
0 skipped**. The broader regression suite covering the existing Knowledge Base,
weather and recommendation integration plus this stage completed with **73
passed, 0 failed, 0 skipped** (one third-party deprecation warning) on
2026-10-14.

Run:

```cmd
docker exec -i wandaraya-api python -m pytest tests/time_context/test_google_period_parser.py tests/time_context/test_source_governance.py -q
```

## Remaining approvals and limitations

Before any acquisition or persistence work, approve source-specific Google
billing/retention/attribution terms, official-site permission and freshness
rules, OSM attribution/licensing and grammar support, manual-review scope, and
the operational update/retention policy. Regular weekly hours still do not
prove temporary closure, safety, accessibility, daylight suitability, duration,
or last-entry conditions.
