# Gate 5E.2D.8A — Commands for Separately Authorized Maintenance

Run one command at a time in Windows CMD from the repository root. Do not concatenate commands.

## 1. Pre-maintenance checks

```cmd
docker compose --profile cutover ps
docker exec -it wandaraya-qdrant-replacement python -c "import requests,json; r=requests.get('http://localhost:6333/collections/sri_lanka_attractions_staging',timeout=30); print(json.dumps(r.json(),indent=2)); r.raise_for_status()"
```

## 2. Apply only the reviewed mount change

Create `qdrant-replacement-snapshots` and add the one reviewed Compose line shown in `gate5e2d8a_change_review.md`. Then validate the Compose file:

```cmd
mkdir qdrant-replacement-snapshots
docker compose --profile cutover config --quiet
```

## 3. Recreate only replacement Qdrant

```cmd
docker compose --profile cutover up -d --force-recreate qdrant-production-replacement
```

## 4. Post-recreation health check

```cmd
docker exec -it wandaraya-qdrant-replacement python -c "import requests,json; r=requests.get('http://localhost:6333/collections/sri_lanka_attractions_staging',timeout=30); print(json.dumps(r.json(),indent=2)); r.raise_for_status()"
curl.exe -sS --max-time 30 http://localhost:8000/health
```

## 5. Create and verify a durable snapshot

```cmd
docker exec -it wandaraya-qdrant-replacement python -c "import requests,json; r=requests.post('http://localhost:6333/collections/sri_lanka_attractions_staging/snapshots',timeout=600); print(json.dumps(r.json(),indent=2)); r.raise_for_status()"
certutil -hashfile "qdrant-replacement-snapshots\<SNAPSHOT_NAME_FROM_API_RESPONSE>" SHA256
```

The API metadata checksum and `certutil` checksum must match. Any mismatch, missing host file, wrong collection name, or degraded collection stops the maintenance operation.
