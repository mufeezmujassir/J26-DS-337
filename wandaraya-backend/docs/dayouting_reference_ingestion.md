# DayOuting.lk reference ingestion

DayOuting is a supplemental source, not the authority of record. The importer
checks the live `robots.txt` before every run. The verified content signal is
`search=yes, ai-train=no, use=reference`; therefore records retain source URLs
and attribution and must never be used for training or fine-tuning a model.
Remote images are referenced by URL only and are not downloaded.

## Flow

1. Read the published single-place and category sitemaps.
2. Fetch structured `TouristAttraction` fragments with a polite delay.
3. Map explicit source categories to the eight WANDARAYA themes.
4. Store every complete record in `tourism_source_staging`.
5. Link exact name-and-district matches to existing official attractions.
6. Use an LLM only for category-ambiguous records; require an allow-listed
   theme and confidence of at least 0.80.
7. Use Google Places for identity verification; reject localities, routes,
   intersections and other non-attraction place types.
8. Promote only approved identities, then embed them into Qdrant.

## Commands

Run inside the API container (or with equivalent database/network settings):

```powershell
docker exec wandaraya-api-cutover python scripts/import_dayouting_attractions.py --delay 0.2

docker exec wandaraya-api-cutover python scripts/import_dayouting_attractions.py `
  --use-staged --llm-review --llm-limit 25

docker exec wandaraya-api-cutover python scripts/import_dayouting_attractions.py `
  --use-staged --google-verify --google-limit 25

docker exec wandaraya-api-cutover python scripts/import_dayouting_attractions.py `
  --use-staged --promote

docker exec -e PYTHONPATH=/app wandaraya-api-cutover python `
  scripts/index_source_attractions.py --source-provider dayouting.lk --new-only
```

Google verification is capped because it uses a billable API. Do not use
`--allow-source-only` unless the source-coordinate records have been manually
reviewed. Rejected or pending staged rows are intentionally invisible to the
recommendation engine.
