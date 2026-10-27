# Official attraction catalogue

WANDARAYA treats the Sri Lanka Tourism catalogue as the attraction identity
authority. Google Places is enrichment-only and cannot create an attraction.
This prevents localities, roads and junctions from entering the recommendation
knowledge base as tourist attractions.

## Source model

- Sitemap catalogue entry: `https://srilanka.travel/attractions`
- Expected catalogue size: 169 official attraction identities
- Official themes: Pristine, Heritage, Wild, Thrills, Bliss, Scenic, Festive,
  and Essence
- Stored source fields: official ID, name, destination, theme, complete
  description, coordinates, useful information, detail URL and image URLs
- Google enrichment: strict name/distance match for address, opening hours,
  rating, telephone and Google Place ID
- Semantic retrieval: the full official description is embedded with
  `BAAI/bge-large-en-v1.5` into the configured Qdrant attraction collection

## Safe rebuild

Create a PostgreSQL custom-format backup first. Then run inside the API
container:

```powershell
docker exec -e PYTHONPATH=/app wandaraya-api-cutover python scripts/rebuild_official_attraction_catalogue.py --execute --confirm-delete-contaminated-attractions --google-enrich --qdrant-url http://qdrant-production-replacement:6333 --qdrant-url http://qdrant:6333
```

When a saved official XML sitemap is available inside the container, add
`--sitemap-file /app/data/srilanka-travel-sitemap.xml`. The importer tolerates
the browser's copied-XML warning and the site's legacy bare ampersands, accepts
only `srilanka.travel` URLs, requires the exact `/attractions` entry, and then
follows the catalogue cards to all 169 dynamic detail pages. General sitemap
pages such as hotels, transport, contacts, and translated duplicates are not
inserted as attractions.

The importer validates all 169 official pages and prepares Google matches
before opening its replacement transaction. It clears only the attraction
domain and attraction-linked mappings. District references, daily weather,
district seasonality, forecasts, holidays and tourism events are preserved.

Rebuild the configured vector collection afterward:

```powershell
docker exec -e PYTHONPATH=/app -e DEBUG=false wandaraya-api-cutover python scripts/rebuild_qdrant_staging.py --execute --confirm-execute --qdrant-url http://qdrant-production-replacement:6333 --collection sri_lanka_attractions_staging --output /tmp/official_catalogue_qdrant_rebuild.json
```

## Required validation

The knowledge-base status must report 169 active attractions and 169 Qdrant
points. The quality endpoint must report zero missing coordinates, districts,
categories, activities and descriptions, and zero duplicate Google Place IDs.
