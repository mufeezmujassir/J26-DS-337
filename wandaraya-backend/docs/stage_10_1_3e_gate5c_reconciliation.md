# Gate 5C — Sri Lanka Tourism catalogue reconciliation

Gate 5C is read-only. It joins the latest completed Sri Lanka Tourism registry
to active WANDARAYA attractions without inserting, updating, deleting, embedding
or indexing anything.

## Actual schema evidence

The current PostgreSQL model provides `attractions.id`, `name`, `slug`,
`google_place_id`, `district_id`, `city`, `latitude`, `longitude`, categories
through `attraction_categories`, and prior description titles/source URLs through
`attraction_descriptions`. There is no dedicated attraction-alias table and no
dedicated external-source-reference column. Gate 5C therefore treats prior
description titles and source URLs as optional alias/external evidence; this
limitation is recorded in the coverage report.

## Matching order

1. Exact previously stored Sri Lanka Tourism source URL.
2. Exact verified Google Place ID, when the catalogue already has one.
3. Exact normalized attraction name.
4. Exact stored alias/description-title match.
5. Exact name plus supplied district/city evidence.
6. Geographic proximity within 1 km, review required.
7. Fuzzy name candidate generation, review required.

Fuzzy and geographic evidence never cause an automatic merge. Ambiguous exact
names such as Ella are retained for review.

## Completed `all_batches_v2` result

The actual active database contained 6,096 attractions at execution time (not
the earlier 222-attraction pilot estimate). The 92 discovered source records had
unique source IDs, unique canonical URLs, normalized names and provenance.

- Existing KB matches: 10
- Probable matches requiring review: 8
- Ambiguous multiple matches: 2
- New attraction candidates: 72
- Insufficient evidence: 0
- Google Places queue records: 82

`new_attraction_candidate` is a review classification, not authorization to
insert a production attraction.

## Commands

Run reconciliation using the latest registry:

```cmd
docker exec -it wandaraya-api python -m scripts.reconcile_srilanka_tourism_catalogue --registry data/reports/stage_10_1_3e_gate5b2_catalogue_all_batches_v2_attraction_registry.json --batch-id all_batches_v2_gate5c_v2
```

Read the coverage summary:

```cmd
docker exec -it wandaraya-api python -c "import json; p='data/reports/stage_10_1_3e_gate5c_all_batches_v2_gate5c_v2_reconciliation_coverage_summary.json'; print(json.dumps(json.load(open(p)), indent=2))"
```

Read the Google Places preparation queue; this does not call Google Places:

```cmd
docker exec -it wandaraya-api python -c "import json; p='data/reports/stage_10_1_3e_gate5c_all_batches_v2_gate5c_v2_google_places_enrichment_queue.json'; print(json.dumps(json.load(open(p)), indent=2))"
```

Run the focused tests:

```cmd
docker exec -it wandaraya-api python -m pytest tests/time_context/test_srilanka_tourism_catalogue_reconciliation.py tests/time_context/test_srilanka_tourism_catalogue_discovery.py tests/time_context/test_srilanka_tourism_gate5b.py -q
```

Gate 5D may consume the queue for Google Places enrichment after its own source
and write controls are implemented.
