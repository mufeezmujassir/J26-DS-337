# Gate 5E.2D.7 — Separately Authorized Snapshot Execution Plan

This plan is intentionally not executed by the Gate 5E.2D.7 command.

1. Confirm the reviewed Compose mount has been applied and the replacement container has been recreated under separate authorization.
2. Verify collection identity and capacity:

```cmd
docker exec -it wandaraya-qdrant-replacement python -c "import requests; r=requests.get('http://localhost:6333/collections/sri_lanka_attractions_staging',timeout=30); print(r.json())"
```

3. Create the snapshot and record the returned name/checksum:

```cmd
docker exec -it wandaraya-qdrant-replacement python -c "import requests,json; r=requests.post('http://localhost:6333/collections/sri_lanka_attractions_staging/snapshots',timeout=600); print(json.dumps(r.json(),indent=2)); r.raise_for_status()"
```

4. Confirm the returned file exists under `qdrant-replacement-snapshots` and compare the API checksum with Windows SHA-256:

```cmd
certutil -hashfile "qdrant-replacement-snapshots\<SNAPSHOT_NAME>" SHA256
```

5. Save the API metadata, checksum, size, timestamp, collection name, Qdrant version, and document-scope hash beside the exported snapshot. A checksum mismatch or missing file stops the process.
