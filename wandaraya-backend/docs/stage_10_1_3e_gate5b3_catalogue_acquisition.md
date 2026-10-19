# Gate 5B.3 — Full catalogue acquisition and consolidation

## Corrected findings from `catalogue_seed_01`

The three saved source captures were inspected offline. The genuine catalogue
cards are scoped to:

```html
<div class="attractions-grid">
  <article class="attraction-card"> ... </article>
</div>
```

Their verified detail links use the legacy source form
`/attraction&attraction_id=<number>`, rather than the global navigation form
`/attraction?attraction_id=<number>`. The corrected adapter converts the legacy
form to the canonical source URL while retaining the original link and card
selector in provenance.

This fixed the prior navigation contamination. The corrected offline rebuild
found 12 real cards on each of the three captured pages and 30 unique source
attraction IDs across them. The three main-content fingerprints differ, so none
of the captured pages is currently marked as a fallback/duplicate response.

The parser now reads the paginator's explicit `Showing 1 to 12 of 169 (15
Pages)` structure. Therefore `12` is treated as a page size, and `169` as the
catalogue-wide total for the general listing. The captured theme-2 response
explicitly reports 69 results; it is retained independently.

No JavaScript endpoint is asserted. The captured pages contain scripts, but the
actual 12 card records and pagination HTML are server-rendered in the saved
responses.

## Current reports

The corrected evidence is stored with a new suffix and does not change prior
reports:

- `data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_pagination_manifest.json`
- `data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_attraction_registry.json`
- `data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_full_discovery_manifest.json`
- `data/reports/stage_10_1_3e_gate5b3_next_batch_01_v5.json`

The registry is Gate 5C-ready: it has the external source ID, preferred and raw
source names, canonical URL, discovery sources, theme evidence, nullable Google
Places fields, nullable existing-KB ID, and a pending read-only reconciliation
status. `Galle Fort` from the verified detail capture is preferred over the
listing alias `Gall Fort`; the raw alias is retained.

## CMD commands

### A. Revalidate the corrected parser against existing captures

```cmd
docker exec -it wandaraya-api python -m scripts.consolidate_srilanka_tourism_catalogue --capture-manifest data/review/srilanka_tourism/catalogue_seed_01/capture_manifest.json --batch-id catalogue_seed_01_corrected_v5_repeat
```

This is offline: zero requests are made.

### B. Generate the next bounded candidate plan

```cmd
docker exec -it wandaraya-api python -m scripts.build_srilanka_tourism_catalogue_next_batch --discovery-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_full_discovery_manifest.json --output-plan config/srilanka_tourism_gate5b3_batch_02.local.json --batch-id catalogue_batch_02 --batch-size 10
```

Edit the generated local plan: enter the real approval reference and timestamp,
then change each selected URL's `authorization_status` to `approved_for_pilot`.

### C. Validate the selected batch

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_catalogue_batch --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b3_batch_02.local.json --catalogue-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_full_discovery_manifest.json --batch-id catalogue_batch_02
```

### D. Execute only when validation has an empty `errors` array

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_catalogue_batch --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b3_batch_02.local.json --catalogue-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_full_discovery_manifest.json --batch-id catalogue_batch_02 --execute --confirm-execute
```

### E. Continue safely after each completed batch

Consolidate all saved catalogue captures, regenerate the manifest, then generate
the following review-only plan. A previously saved capture is skipped through
the acquired-URL list, and an existing batch ID is rejected before a request.

```cmd
docker exec -it wandaraya-api python -m scripts.consolidate_srilanka_tourism_catalogue --capture-root data/review/srilanka_tourism --batch-id catalogue_all_batches_v1
docker exec -it wandaraya-api python -m scripts.build_srilanka_tourism_catalogue_next_batch --discovery-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_all_batches_v1_full_discovery_manifest.json --output-plan config/srilanka_tourism_gate5b3_next.local.json --batch-id catalogue_batch_next --batch-size 10
```

### F. Display unique source records and coverage

```cmd
docker exec -it wandaraya-api python -c "import json; s=json.load(open('data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_catalogue_discovery_summary.json')); print(json.dumps(s, indent=2))"
```

No command in this stage writes PostgreSQL or Qdrant.
