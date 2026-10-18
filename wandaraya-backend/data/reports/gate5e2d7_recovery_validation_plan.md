# Gate 5E.2D.7 — Isolated Snapshot Recovery Validation Plan

Use a disposable container, a **new** Docker volume, and Qdrant `v1.19.1`. Never target `wandaraya-qdrant-replacement` or its `qdrant_staging_data` volume.

```powershell
docker volume create wandaraya_qdrant_recovery_verify_data
docker run -d --name wandaraya-qdrant-recovery-verify -p 127.0.0.1:6336:6333 -v wandaraya_qdrant_recovery_verify_data:/qdrant/storage -v "${PWD}\qdrant-replacement-snapshots:/qdrant/snapshots:ro" qdrant/qdrant:v1.19.1
```

Restore only into the disposable container using the exported snapshot. Then run the existing read-only validator against `http://localhost:6336` and `sri_lanka_attractions_staging`. Required checks are: 6,120 points, full scroll, filtered scroll, direct retrieval, 1,024 dimensions, and vector search. Destroy the disposable container/volume only after an explicit review; do not touch production.
