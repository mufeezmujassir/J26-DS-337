# Stage 10.1.3D — Controlled Sri Lanka Tourism Live Acquisition

**Status:** COMPLETE_WITH_LIMITATIONS — implementation and dry run only. No
live crawler was launched.

The new `live_pilot` module implements a bounded plan: HTTPS
`srilanka.travel`/`www.srilanka.travel` only, normalized/canonicalized URLs,
duplicate rejection, max 10 pages, concurrency one, minimum three-second
request spacing, one retry maximum, response-size/timeout configuration, and
an emergency stop. It deliberately does not contain a method that performs an
HTTP request. A separate, explicit technical execution approval plus an exact
approved URL plan is required before any future fetcher can be connected.

HTML is accepted only as a caller-supplied fixture in this stage. Extraction is
deterministic (title, canonical link, h1, main/article description and known
JSON-LD presence); facts retain a source URL and unknown fields stay null.
Staging returns content hash and review metadata only. It performs no production
table update, opening-hours overwrite, entity creation, embedding or Qdrant
write.

The source authorization record now distinguishes researcher-reported verbal
scope from documentary evidence and technical execution approval. Reported
permission is not written authorization, and redistribution/commercial terms
remain unapproved.

## Live-pilot prerequisites

1. Record grantor/department and permission date if known.
2. Obtain/document exact domains, content types, retention, attribution,
   embedding, redistribution, commercial-use, rate-limit and access scope.
3. Enter an explicit researcher execution-approval timestamp.
4. Review approved navigation/sitemap pages and create an exact URL plan.
5. Confirm robots/access policy and emergency-stop process.
6. Run dry run, then separately authorize at most ten monitored pages.

No real extraction rate, HTTP success rate, coverage, latency, cost, or source
agreement is claimed because no live acquisition was executed.

Offline validation completed with **69 focused tests** and **91 broader
regression tests** passing; no tests failed or were skipped. One third-party
deprecation warning was emitted by the broader suite.
