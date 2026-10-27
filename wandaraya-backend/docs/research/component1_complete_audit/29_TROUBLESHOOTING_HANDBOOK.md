# Troubleshooting Handbook

| Symptom | Diagnostic | Safe resolution |
|---|---|---|
| Docker unavailable | `docker version`; `docker compose ps` | start Docker Desktop; do not delete volumes |
| FastAPI startup fails | `docker compose logs --tail 200 fastapi-cutover` | fix reported env/import/dependency |
| DB error | health; inspect Postgres service/logs | verify `DATABASE_URL`, service DNS and migrations |
| Qdrant error/empty | KB status; inspect API container env | use replacement service/collection; do not rebuild during demo |
| dimension mismatch | compare model dimension and collection config | create validated new collection and re-embed in controlled migration |
| feature endpoint 503 | inspect non-secret feature flags | enable only isolated research flags; leave production false |
| 401/403 | confirm local headers/session owner | correct token/owner; do not print secret |
| graph 504 | inspect node/tool latency | reduce candidate count or repair slow adapter; timeout is 45 s |
| missing seasonality | inspect mapping/profile/evidence status | treat as unavailable; repair data pipeline, not score fabrication |
| weather unavailable | inspect selected source/date/approval | use valid source; do not call climatology a forecast |
| empty semantic results | validate nonblank query, collection/counts | check active collection and PostgreSQL/Qdrant consistency |
| slow first request | model load/cache logs | warm model before demo; monitor memory |
| OOM | container stats/model process | lower concurrency/candidate pool; allocate RAM |
| Alembic error | `alembic current`; `alembic history` | back up and resolve revision; never stamp blindly |
| SQLAlchemy session error | stack trace and concurrent use | keep shared-session adapters sequential as implemented |
| missing LangChain import | `pip show langgraph langchain-core langchain-openai` | install pinned requirements in correct environment |
| LLM provider error | keep optional parser disabled; inspect sanitized error | deterministic parser remains available |
| test import failure | `python -m pytest --collect-only -q` | use project interpreter and install requirements |

Relevant sources: `app/config.py`, `app/main.py`, both research routers, unified orchestrator, graph service, embedding/indexer, source selector, and Compose. Preserve data and collect diagnostics before any repair.

