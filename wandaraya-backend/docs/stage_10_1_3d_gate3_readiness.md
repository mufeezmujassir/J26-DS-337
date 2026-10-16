# Stage 10.1.3D Gate 3 — Live-Pilot Readiness

**Status:** READY_FOR_SEPARATELY_CONFIRMED_ONE_PAGE_PILOT.

## Configuration inspection

The researcher-owned local file is valid JSON and is visible inside the
`wandaraya-api` container. It records researcher-confirmed verbal permission
for academic collection, storage, processing and embeddings; the evidence
status remains `undocumented`. It records a timezone-aware technical execution
approval timestamp: `2026-10-14T12:30:00+05:30`.

The exact one-page plan is syntactically valid HTTPS and canonicalizes to
`https://srilanka.travel/`. Its hostname is present in the configured approved
domains. No sitemap or additional page was assumed.

## Authorization record and remaining limitations

The researcher has now recorded the following as `source_confirmed` for the
limited homepage pilot:

- retention conditions;
- attribution conditions; and
- request-rate restrictions.

The configuration therefore passes the automated authorization gate. The
permission evidence remains verbal and `undocumented`; it should be supported
by a written source reply when available. A non-empty condition string alone
still does not pass the gate—each status must be explicitly
`source_confirmed`. The contact template remains available in
`docs/srilanka_tourism_source_confirmation_request.md`.

## Safety controls retained

The executor remains limited to ten pages, one concurrent request, a minimum
three-second interval, one retry, HTTPS exact URL allowlisting, redirect review,
emergency stop, response-size limits, and HTML/XML content-type validation.
It only creates review-stage content hashes; it does not write production
attractions, embeddings, or Qdrant points.

## Commands

Dry run (no network):

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_pilot --config config/srilanka_tourism_pilot.local.json
```

Only after all source conditions are confirmed and the dry run reports an empty
`errors` list, the separately approved homepage pilot command is:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_pilot --config config/srilanka_tourism_pilot.local.json --execute --confirm-execute
```
