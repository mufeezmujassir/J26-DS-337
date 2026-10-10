import asyncio
import secrets

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import settings
from app.database import AsyncSessionLocal
from app.knowledge_base.refresh.refresh_service import TourismKBRefreshService
from app.knowledge_base.discovery.discovery_service import (
    NationwideAttractionDiscoveryService,
)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "db": "ok", "redis": "ok", "qdrant": "ok"}


_kb_refresh_lock = asyncio.Lock()
_kb_discovery_lock = asyncio.Lock()


class DiscoveryRequest(BaseModel):
    max_cells: int | None = Field(default=None, ge=1)
    max_types: int | None = Field(default=None, ge=1)
    ingest: bool = True


@app.post("/internal/knowledge-base/refresh")
async def refresh_knowledge_base(
    x_airflow_token: str | None = Header(default=None),
):
    configured_token = settings.AIRFLOW_API_TOKEN
    if len(configured_token) < 32:
        raise HTTPException(
            status_code=503,
            detail="Airflow API authentication is not configured.",
        )

    if x_airflow_token is None or not secrets.compare_digest(
        x_airflow_token.encode("utf-8"),
        configured_token.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Unauthorized.")

    if _kb_refresh_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A knowledge-base refresh is already running.",
        )

    await _kb_refresh_lock.acquire()
    try:
        async with AsyncSessionLocal() as db:
            result = await TourismKBRefreshService(db=db).refresh(limit=3)

        return {
            "requested": result.requested,
            "successful": result.successful,
            "skipped": result.skipped,
            "failed": result.failed,
            "refreshed_attraction_ids": result.refreshed_attraction_ids,
            "errors": result.errors,
            "started_at": result.started_at.isoformat(),
            "finished_at": (
                result.finished_at.isoformat()
                if result.finished_at
                else None
            ),
        }
    finally:
        _kb_refresh_lock.release()


@app.post("/internal/knowledge-base/discovery")
async def discover_knowledge_base(
    request: DiscoveryRequest,
    x_airflow_token: str | None = Header(default=None),
):
    configured_token = settings.AIRFLOW_API_TOKEN
    if len(configured_token) < 32:
        raise HTTPException(
            status_code=503,
            detail="Airflow API authentication is not configured.",
        )
    if x_airflow_token is None or not secrets.compare_digest(
        x_airflow_token.encode("utf-8"),
        configured_token.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Unauthorized.")
    if _kb_discovery_lock.locked():
        raise HTTPException(status_code=409, detail="A knowledge-base discovery run is already running.")

    await _kb_discovery_lock.acquire()
    try:
        async with AsyncSessionLocal() as db:
            result = await NationwideAttractionDiscoveryService().run(
                db=db,
                max_cells=request.max_cells,
                max_types=request.max_types,
                ingest=request.ingest,
            )

        ingestion = result.ingestion
        return {
            "discovered": result.discovered_count,
            "already_known": len(result.existing_place_ids),
            "new": len(result.new_place_ids),
            "ingested_successfully": ingestion.success if ingestion else 0,
            "ingested_skipped": ingestion.skipped if ingestion else 0,
            "ingested_failed": ingestion.failed if ingestion else 0,
            "errors": result.errors,
        }
    finally:
        _kb_discovery_lock.release()



from app.routers import route_validation
app.include_router(route_validation.router, prefix="/api")

# You can include your routers here later:
# from app.routers import recommend
# app.include_router(recommend.router, prefix="/api")
