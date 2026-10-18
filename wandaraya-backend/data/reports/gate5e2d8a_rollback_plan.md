# Gate 5E.2D.8A — Rollback Plan

## Configuration rollback

If the replacement fails its health check after recreation, remove only the added snapshot bind-mount line from `qdrant-production-replacement` and recreate only that service:

```cmd
docker compose --profile cutover up -d --force-recreate qdrant-production-replacement
docker exec -it wandaraya-qdrant-replacement python -c "import requests; r=requests.get('http://localhost:6333/collections/sri_lanka_attractions_staging',timeout=30); print(r.status_code); r.raise_for_status()"
```

This retains `wandaraya-backend_qdrant_staging_data`; do not use `docker volume rm`, do not start the old Qdrant, and do not restore the legacy snapshot.

## Data recovery validation

Restore any newly created replacement snapshot only into a separately named disposable container and volume. A production restore requires a new, separate authorization.

## Protected assets

Keep `qdrant-data-quarantine-2026-10-18` and `qdrant-snapshots/sri_lanka_attractions-1336472673414113-2026-10-18-07-30-23.snapshot` untouched throughout rollback and later review.
