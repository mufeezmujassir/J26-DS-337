# Gate 5D — Google Places identity verification

Gate 5D is a read-only, review-only step between the Sri Lanka Tourism catalogue and a future write-enabled Gate 5E. It reuses the existing Google Places API (New) connector (`/v1/places:searchText` and optional Place Details) and the environment variable `GOOGLE_PLACES_API_KEY`. Keys are never written to reports.

The default command is offline: it performs no Google request, PostgreSQL write, Qdrant write, embedding generation, merge, or update. It validates the bounded queue, reads existing attractions only, and produces a manifest that marks records as `insufficient_evidence` because they were not queried.

Candidate evidence is scored from normalized original/alternative names, source-supported locality, source coordinates when present, type presence, and existing Google Place ID equality. Only exact existing Google Place ID equality produces `verified_existing_kb_match`. Similar names remain `high_confidence_candidate_review`, `ambiguous_multiple_candidates`, or `new_google_place_candidate`; none is merged automatically.

## Commands (Windows CMD)

Offline five-record validation:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_google_places_gate5d --batch-id pilot_01 --max-records 5
```

Prepare the next bounded offline batch (offset five):

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_google_places_gate5d --batch-id pilot_02 --max-records 5 --offset 5
```

Human-controlled live pilot, only after the researcher explicitly decides to spend API quota:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_google_places_gate5d --batch-id pilot_01_live --max-records 5 --max-candidates 5 --request-interval-seconds 1 --max-retries 1 --include-details --live --execute --confirm-execute
```

View the summary:

```cmd
docker exec -it wandaraya-api python -c "import json; print(json.dumps(json.load(open('data/reports/stage_10_1_3e_gate5d_pilot_01_google_places_discovery_summary.json')), indent=2))"
```

The twelve batch reports share the prefix `stage_10_1_3e_gate5d_<batch_id>_google_places_`: discovery summary, candidate matches, verified matches, ambiguous matches, new candidates, no-match, enrichment results, field provenance, duplicate clusters, human-review queue, API usage, and full manifest.

Limitations: a source record without locality or coordinates cannot gain those fields from inference; Google API results are proposals, not proof; every non-exact identity needs review. The existing attraction schema has no dedicated alias/external-reference table, so its description titles and URLs are read only as limited supporting evidence.
