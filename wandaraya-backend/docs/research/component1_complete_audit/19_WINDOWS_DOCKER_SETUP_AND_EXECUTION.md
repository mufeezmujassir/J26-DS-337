# Windows, Docker Setup and Execution

From PowerShell in the repository root:

```powershell
docker compose config --services
docker compose up -d
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1/knowledge-base/status
```

Expected health structure is `{status:'ok', db:'ok', redis:'ok', qdrant:'ok'}`; this was observed during the audit. Services include PostGIS, Redis, legacy and replacement Qdrant, FastAPI cutover, Airflow, Airflow metadata PostgreSQL, MinIO and pgAdmin. Exact names should come from `docker compose ps`, not old documentation.

Run tests without mutating persistent services:

```powershell
python -m pytest tests/agents -q
python -m pytest tests -q
```

Before a full test run, inspect fixtures for DB writes and use the test environment. Do not delete volumes, recreate collections or run ingestion merely to prove startup.

The active API container uses replacement Qdrant internally. Use the KB API for routine validation; direct `localhost:6333` reaches the legacy service in the audited Compose layout. Configuration comes from `.env` through Pydantic settings (`app/config.py:55`); never paste secret values into slides or logs.

For Airflow, open its configured web port from `docker compose ps`, inspect DAG state there, and distinguish parsed/configured DAGs from successful task runs. The audit did not trigger paid connectors or ingestion jobs.

