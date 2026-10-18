# Gate 5E.2D.7 — Durable Qdrant Snapshot Persistence Plan

## Current evidence

- Active replacement container: `wandaraya-qdrant-replacement`
- Collection: `sri_lanka_attractions_staging`
- Data volume: `wandaraya-backend_qdrant_staging_data` mounted at `/qdrant/storage`
- A `/qdrant/snapshots` mount is currently absent.
- Legacy snapshot remains preserved at `qdrant-snapshots/sri_lanka_attractions-1336472673414113-2026-10-18-07-30-23.snapshot`. It must not be used as the replacement recovery point because its isolated restore previously failed.
- The prior staging snapshot metadata is recorded, but it is not visible to the active replacement service.

## Reviewed configuration change — do not apply without separate authorization

Add this **additional** mount to `qdrant-production-replacement`; retain the existing data-volume mount unchanged:

```yaml
    volumes:
      - qdrant_staging_data:/qdrant/storage
      - ./qdrant-replacement-snapshots:/qdrant/snapshots
```

The new host directory is dedicated to replacement snapshots. It must never be `qdrant-data`, the quarantine directory, or the legacy snapshot directory.

## Storage assessment

- Host free capacity observed: `3171004416` bytes
- Conservative required capacity: `1779322880` bytes
- Assessment: `sufficient`

## Retention

Keep at least the two newest validated replacement snapshots and their SHA-256 manifests. Retain the quarantine directory and legacy snapshot until a separate rollback-retention sign-off. Do not overwrite a snapshot filename.
