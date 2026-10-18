# Stage 10.1.3E Gate 5B.1 — Listing Quality and Attraction Details

## Completed offline correction

The already captured `/attractions` report was repaired without a refetch. Its
generic first paragraph was attraction-card text and is no longer represented
as a listing-page description. `listing_description` is now `null` unless a
listing-scoped intro selector is present. The record carries
`listing_card_description_removed_from_page_scope` for review.

Attraction references preserve both `link_text_original` and normalised
`link_text_normalized`; no spelling correction is applied. In particular,
`Gall Fort` remains source text until separately supported.

## Detail extraction rules

Yala and Sigiriya detail pages are prepared but not acquired. Detail fields are
populated only from explicit page labels in table or definition-list structures.
Unsupported or absent values remain null/empty. Conflicting location labels,
unparseable labelled opening hours, empty descriptions, and missing names create
review warnings. Source ID, URL, timestamp, hash, selector evidence and excerpt
remain attached to every populated field.

## Two-page plan

Copy the separate template, add the researcher's actual approval reference and
timezone-aware timestamp, and explicitly mark both URLs `approved_for_pilot`:

```cmd
copy config\srilanka_tourism_gate5b_detail_plan.example.json config\srilanka_tourism_gate5b_detail_plan.local.json
notepad config\srilanka_tourism_gate5b_detail_plan.local.json
```

Offline plan validation (zero network requests):

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_gate5b --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b_detail_plan.local.json
```

Only after the validation reports `"errors": []`:

```cmd
docker exec -it wandaraya-api python -m scripts.run_srilanka_tourism_gate5b --authorization-config config/srilanka_tourism_pilot.local.json --plan config/srilanka_tourism_gate5b_detail_plan.local.json --execute --confirm-execute
```

The screenshot search URL and its pagination are not in the Gate 5A manifest
or this exact-URL plan. They need a later separately reviewed manifest and
explicit approval; Gate 5B.1 does not crawl all listing/search pages.

## All currently observed listing details

The captured `/attractions` listing exposed six distinct attraction-detail URLs.
Generate its review-only manifest and two exact three-page batches without a
network request:

```cmd
docker exec -it wandaraya-api python -m scripts.build_srilanka_tourism_detail_batches
```

The output files are `data/reports/stage_10_1_3e_gate5b1_detail_batch_01.json`
and `data/reports/stage_10_1_3e_gate5b1_detail_batch_02.json`. Each still needs
its own researcher approval reference and timestamp before execution. This
covers only the URLs observed in the already captured listing; it does not claim
to include all attractions available through unacquired search or pagination
pages.
