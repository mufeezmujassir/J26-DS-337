# Gate 5B.3 — Batch configuration and execution workflow

## Diagnosis

The original Batch 02 file was a deliberately incomplete review plan. It had
no `approval_reference`, no `researcher_execution_approved_at`, and every URL
was `discovered_unapproved`. It also lacked a batch ID and source-manifest
provenance. The base source authorization file correctly contained only the
homepage in `exact_urls`; it must not be modified just to run a catalogue batch.

A batch now has two separate local files:

1. A batch plan with selected URLs, batch ID, source manifest path/checksum, and
   researcher-confirmed batch approval.
2. A batch-scoped authorization configuration that retains the original source
   permission, approved domains, source-confirmed conditions and rate limits,
   but uses exactly the selected URLs. It does not overwrite the base config.

The validator requires the two URL lists to match. It also verifies the stored
source-manifest checksum, preventing a plan generated from one report version
from silently being executed against another.

## Batch 02 — Windows CMD commands

Replace the two approval values below with the real batch approval reference and
real timezone-aware timestamp. This preparation command is offline only.

```cmd
docker exec -it wandaraya-api python -m scripts.prepare_srilanka_tourism_catalogue_batch --authorization-config config/srilanka_tourism_pilot.local.json --discovery-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_full_discovery_manifest.json --batch-id catalogue_batch_02 --output-plan config/srilanka_tourism_gate5b3_batch_02.prepared.local.json --output-authorization-config config/srilanka_tourism_gate5b3_batch_02.authorization.local.json --approval-reference "REPLACE_WITH_REAL_BATCH_02_APPROVAL" --researcher-execution-approved-at "REPLACE_WITH_REAL_ISO8601_TIMESTAMP" --batch-size 10
```

For example, an actual timestamp is formatted like `2026-10-16T18:30:00+05:30`.
Do not use the placeholder text as approval evidence.

Validate without a request:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_catalogue_batch --authorization-config config/srilanka_tourism_gate5b3_batch_02.authorization.local.json --plan config/srilanka_tourism_gate5b3_batch_02.prepared.local.json --catalogue-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_full_discovery_manifest.json --batch-id catalogue_batch_02
```

Only when `errors` is empty, execute the approved batch:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_catalogue_batch --authorization-config config/srilanka_tourism_gate5b3_batch_02.authorization.local.json --plan config/srilanka_tourism_gate5b3_batch_02.prepared.local.json --catalogue-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_seed_01_corrected_v5_full_discovery_manifest.json --batch-id catalogue_batch_02 --execute --confirm-execute
```

## Repeating batches

After a completed acquisition, rebuild the current state from immutable saved
catalogue captures. This has no network activity:

```cmd
docker exec -it wandaraya-api python -m scripts.consolidate_srilanka_tourism_catalogue --capture-root data/review/srilanka_tourism --batch-id catalogue_all_batches_v2
```

Prepare Batch 03 from that exact new manifest. The generator skips every URL
already present in saved catalogue captures and selects at most ten pending URLs.

```cmd
docker exec -it wandaraya-api python -m scripts.prepare_srilanka_tourism_catalogue_batch --authorization-config config/srilanka_tourism_pilot.local.json --discovery-manifest data/reports/stage_10_1_3e_gate5b2_catalogue_all_batches_v2_full_discovery_manifest.json --batch-id catalogue_batch_03 --output-plan config/srilanka_tourism_gate5b3_batch_03.prepared.local.json --output-authorization-config config/srilanka_tourism_gate5b3_batch_03.authorization.local.json --approval-reference "REPLACE_WITH_REAL_BATCH_03_APPROVAL" --researcher-execution-approved-at "REPLACE_WITH_REAL_ISO8601_TIMESTAMP" --batch-size 10
```

Repeat preparation, offline validation, and explicit execution until the latest
consolidated report has `pages_remaining: 0`.

Display final source-record coverage:

```cmd
docker exec -it wandaraya-api python -c "import json; p='data/reports/stage_10_1_3e_gate5b2_catalogue_all_batches_v2_catalogue_discovery_summary.json'; print(json.dumps(json.load(open(p)), indent=2))"
```

All discovery files remain review-only. PostgreSQL, Qdrant, Google Places, and
embedding writes remain outside Gate 5B.3.
