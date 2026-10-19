# Stage 10.1.3D Gate 2 — Controlled URL Discovery and Live-Pilot Guard

**Status:** COMPLETE_WITH_LIMITATIONS. Gate 2 implements the guard and dry-run
workflow; it did not discover or fetch a live page.

## Authorization template

Copy `config/srilanka_tourism_pilot.example.json` to a non-committed local file
and complete every material field: reported permission scope, permitted content
categories, retention and attribution conditions, request restrictions, exact
HTTPS URLs, approved domains, and researcher execution timestamp. Unknown facts
must remain null, and missing material conditions deliberately block execution.

Each material condition also has a `*_status`. A value marked
`researcher_proposed` is recorded for governance but **does not** authorize a
live request. Only a non-empty condition marked `source_confirmed` passes the
source-condition gate. This prevents a research-team operating limit from being
misrepresented as a source-approved restriction.

The recorded authorization remains researcher-confirmed verbal permission with
undocumented evidence. It is not a written licence. Commercial and redistribution
use remain unapproved unless separately documented.

## Commands

Dry run — no network request:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_pilot --config config/srilanka_tourism_pilot.local.json
```

Only after a separate researcher authorization, execute the exact approved plan:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_pilot --config config/srilanka_tourism_pilot.local.json --execute --confirm-execute
```

The executor accepts only exact HTTPS URLs in the configured approved domains,
at most ten pages, one request at a time, at least three seconds apart, with one
retry maximum. Redirect destinations require separate exact-plan review. It
does not update attraction tables, generate embeddings, or write Qdrant points;
it emits review-only content-hash staging metadata.

## Discovery

The future discovery mechanism must begin only with an approved homepage or
explicitly approved sitemap URL, then normalize, deduplicate and classify links
inside the configured domain. The candidate `https://srilanka.travel/sitemap.xml`
is not assumed to exist and has not been requested. Unrelated domains,
authentication/CAPTCHA barriers, robots/access restrictions, large media, and
unapproved redirects are rejected.

Fixture-only Gate 2 and broader regression validation completed with **93
passed, 0 failed, 0 skipped**. One third-party deprecation warning was emitted.
