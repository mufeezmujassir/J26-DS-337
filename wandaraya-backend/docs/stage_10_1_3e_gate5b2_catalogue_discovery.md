# Gate 5B.2 — Sri Lanka Tourism catalogue discovery

## Purpose and boundaries

Gate 5B.2 expands discovery beyond the first six observed attraction links. It
is an offline-first, review-only catalogue process. It does not create or update
PostgreSQL attraction records, call Google Places, create embeddings, or write
to Qdrant.

The three initial URL forms are deliberately represented as distinct potential
source structures until their captured HTML proves otherwise:

- `https://www.srilanka.travel/attractions`
- `https://srilanka.travel/tourist-attractions?page=2`
- `https://srilanka.travel/index.php?route=attractions/attractions-search&theme=2`

The seed manifest records these as separate **unobserved** inputs. It does not
claim that page 2 exists, that theme 2 is a valid filter, or that the URLs cover
the full catalogue.

## Discovery rules

Only a link with a verified `attraction_id` becomes an attraction-card record.
This excludes navigation links. A card may have only a name, source URL and
source attraction ID; missing descriptions, categories, destination, opening
hours, fees and coordinates are accepted as null.

Pagination and theme/category/destination controls are included only when their
links are present in captured HTML. The parser reports script and AJAX/load-more
markers, but does not execute JavaScript or invent unseen pages.

Records are merged by verified `external_source_id`; canonical URL is a stable
secondary identity. Source records lacking an ID are kept in the unresolved
report rather than being silently merged. Google Places fields remain null and
are merely prepared for the following enrichment stage.

## Commands

Build the review-only seed manifest (no network):

```powershell
docker exec -it wandaraya-api python -m scripts.build_srilanka_tourism_catalogue_manifest
```

Create your researcher-owned local batch plan from the template, then enter a
real approval reference and timezone-aware approval timestamp. Do not commit the
local plan. The following command is for **Windows CMD** (your current prompt).

```cmd
copy /Y config\srilanka_tourism_gate5b2_catalogue_plan.example.json config\srilanka_tourism_gate5b2_catalogue_plan.local.json
```

Then edit `config\srilanka_tourism_gate5b2_catalogue_plan.local.json` and replace
both placeholder values. `researcher_execution_approved_at` must be a real
timezone-aware value such as `2026-10-16T18:30:00+05:30`; do not leave the
placeholder text in the JSON.

Validate a selected batch without a request:

```powershell
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_catalogue_batch --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b2_catalogue_plan.local.json --catalogue-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_seed_manifest.json --batch-id catalogue_seed_01
```

Execute only after the validation output contains no errors. This is the sole
command below that makes live requests. It retains exact URLs, concurrency 1,
at least a 3-second interval, one retry, response-size and content-type checks,
and the maximum 10-page limit.

```powershell
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_catalogue_batch --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b2_catalogue_plan.local.json --catalogue-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_seed_manifest.json --batch-id catalogue_seed_01 --execute --confirm-execute
```

The live batch saves immutable HTML fixtures and batch-specific reports. It
refuses an already-used batch ID before making a request.

Consolidate one or more saved capture manifests without network access:

```powershell
docker exec -it wandaraya-api python -m scripts.consolidate_srilanka_tourism_catalogue --capture-manifest data/review/srilanka_tourism/catalogue_seed_01/capture_manifest.json --batch-id catalogue_consolidated_01
```

For multiple batches, repeat `--capture-manifest` once per saved manifest.
The consolidation creates seven batch-specific reports: discovery summary,
pagination manifest, theme-search manifest, deduplicated registry, coverage,
unresolved references, and human review queue.

Run the focused tests:

```powershell
docker exec -it wandaraya-api python -m pytest tests/time_context/test_srilanka_tourism_catalogue_discovery.py tests/time_context/test_srilanka_tourism_gate5b.py -q
```
