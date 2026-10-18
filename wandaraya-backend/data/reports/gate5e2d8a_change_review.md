# Gate 5E.2D.8A — Final Production Snapshot Change Review

## Active configuration

- Compose service: `qdrant-production-replacement`
- Active container: `wandaraya-qdrant-replacement`
- Image: `qdrant/qdrant:v1.19.1`
- Collection: `sri_lanka_attractions_staging`
- Active Compose files: `docker-compose.yml`

### Current mounts

- `volume` `wandaraya-backend_qdrant_staging_data` → `/qdrant/storage`

The persistent data volume remains unchanged. The proposed bind mount is additional and targets `/qdrant/snapshots`, not `/qdrant/storage`.

## Minimal reviewed diff — not applied

```diff
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ qdrant-production-replacement
     volumes:
       - qdrant_staging_data:/qdrant/storage
+      - ./qdrant-replacement-snapshots:/qdrant/snapshots
```

## Host path and capacity

- Intended host snapshot directory: `C:\Users\MUFEEZ\OneDrive - Sri Lanka Institute of Information Technology\Desktop\RP\Research_2027\wandaraya-backend\qdrant-replacement-snapshots`
- Directory exists now: `False`
- Parent directory writable: `True`
- Free bytes: `6039887872`
- Conservative required bytes: `1779322880`

The directory must be created only during the separately authorized maintenance operation. It is deliberately not created during this review.

## Expected impact

Only the replacement Qdrant container is recreated. PostgreSQL, Redis, FastAPI, Qdrant points, and the persistent data volume are unchanged. Semantic requests can return controlled Qdrant-unavailable responses while Qdrant restarts; plan a short maintenance window. Expected interruption is normally tens of seconds, but it is not guaranteed and must be measured during execution.

## Protected legacy assets

- `qdrant-snapshots/sri_lanka_attractions-1336472673414113-2026-10-18-07-30-23.snapshot` remains untouched.
- `qdrant-data-quarantine-2026-10-18` remains untouched.
- No production restore is part of this change.
