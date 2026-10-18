# Gate 5B.1 — Extraction Quality Fix

## Finding

Batch 01 successfully fetched the three approved attraction-detail URLs, but its
review reports retained only extracted metadata.  `raw_content` was deliberately
kept in memory during the live request and excluded from report serialization.
Consequently, the Batch 01 HTML cannot be inspected or reprocessed offline.
This is an evidence-retention limitation, not evidence that a source page has no
description, location, category, or other detail.

The original Batch 01 reports remain unchanged:

- `data/reports/stage_10_1_3e_gate5b_acquisition_results.json`
- `data/reports/stage_10_1_3e_gate5b_extraction_results.json`
- `data/reports/stage_10_1_3e_gate5b_field_completeness.json`

They record 3 pages, 51 reported fields, 9 populated source-supported fields,
and 42 unknown fields (17.6% completeness).  Each page supplied only its title,
URL attraction ID, and attraction name to the v1 extractor.

## Correction

The `gate5b_v2` detail adapter now accepts only evidence from source-specific
detail selectors or embedded JSON-LD for descriptions:

- `[data-attraction-description]`
- `.attraction-description`
- `.attraction-details .description`
- `#attraction-description`
- `[itemprop='description']`
- `application/ld+json` `description`

It extracts location, district, category, activities, operating information,
fees, seasonal information, accessibility and contact details only from explicit
`table th/td` or `dt/dd` label/value pairs.  Each accepted value carries selector
or label provenance and an excerpt.  It does not promote arbitrary card or
generic paragraph text to a detail description.

If none of the supported detail containers, JSON-LD values, or labelled fields
are present, the record is marked with
`detail_content_not_found_by_known_selectors_or_labels_possible_javascript_dependency`.
That warning means **extractor evidence is incomplete**; it does not claim the
field is genuinely absent from the page.  A captured fixture and human review
are required to decide whether the page is JavaScript-dependent or needs an
additional verified selector.

## Reproducible re-acquisition procedure

No live request is made by this change.  Because Batch 01 did not retain HTML,
the researcher may make a separately approved re-acquisition using its existing
three-URL plan.  Choose a never-before-used batch ID; fixture directories are
immutable and checked before any request is made.

```powershell
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_gate5b --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b_batch_01.local.json --manifest data/reports/stage_10_1_3e_gate5b1_detail_manifest.json --execute --confirm-execute --batch-id batch01_reacquire_v2
```

That command saves review-only fixtures under
`data/review/srilanka_tourism/batch01_reacquire_v2/` and writes new,
batch-specific `stage_10_1_3e_gate5b_batch01_reacquire_v2_*.json` reports.  It
does not write PostgreSQL or Qdrant.

Validate checksums and re-extract all captured pages without network access:

```powershell
docker exec -it wandaraya-api python -m scripts.extract_srilanka_tourism_capture_batch --capture-manifest data/review/srilanka_tourism/batch01_reacquire_v2/capture_manifest.json --plan config/srilanka_tourism_gate5b_batch_01.local.json --manifest data/reports/stage_10_1_3e_gate5b1_detail_manifest.json --batch-id batch01_reacquire_v2_offline
```

Inspect the resulting records, selector diagnostics, field provenance, and
completeness report:

```powershell
docker exec -it wandaraya-api python -c "import json; p='data/reports/stage_10_1_3e_gate5b_batch01_reacquire_v2_offline_extraction_results.json'; print(json.dumps(json.load(open(p)), indent=2))"
docker exec -it wandaraya-api python -c "import json; p='data/reports/stage_10_1_3e_gate5b_batch01_reacquire_v2_offline_field_completeness.json'; print(json.dumps(json.load(open(p)), indent=2))"
```

## Expected before/after interpretation

The baseline is 9 populated out of 51 fields.  The re-acquisition result—not a
prediction—will establish the v2 count.  Values with field provenance are
explicitly supported.  Null values plus selector diagnostics identify either
source absence or a parsing/JavaScript question that still needs review.

## Verification

Run the offline extractor tests:

```powershell
docker exec -it wandaraya-api python -m pytest tests/time_context/test_srilanka_tourism_gate5b.py -q
```

The tests use synthetic captured HTML only; they make no network request and
perform no PostgreSQL or Qdrant write.
