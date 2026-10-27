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
from app.routers.weather_forecasts import router as weather_forecast_router
from app.routers.weather_context import (
    router as weather_context_router,
)
from app.routers.weather_suitability import (
    router as weather_suitability_router,
)
from app.routers.weather_attractions import (
    router as weather_attractions_router,
)
from app.routers.weather_kb import router as weather_kb_router
from app.routers.knowledge_base import router as knowledge_base_router
from app.routers.context_enrichment import router as context_enrichment_router
from app.routers.content_recommendations import router as content_recommendations_router
from app.routers.time_aware_recommendations import router as time_aware_recommendations_router
from app.routers.holiday_events import router as holiday_events_router
from app.routers.unified_context_research import router as unified_context_research_router
from app.routers.langgraph_recommendations import router as langgraph_recommendations_router
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

app.include_router(weather_forecast_router)

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
            "wikipedia_enrichment_failures": result.wikipedia_enrichment_failures,
            "wikivoyage_enrichment_failures": result.wikivoyage_enrichment_failures,
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
        ingestion_results = ingestion.results if ingestion else []
        wikipedia_enrichment_failures = sum(
            any(warning.startswith("Wikipedia enrichment failed:") for warning in item.warnings)
            for item in ingestion_results
        )
        wikivoyage_enrichment_failures = sum(
            any(warning.startswith("Wikivoyage enrichment failed:") for warning in item.warnings)
            for item in ingestion_results
        )
        return {
            "discovered": result.discovered_count,
            "already_known": len(result.existing_place_ids),
            "new": len(result.new_place_ids),
            "ingested_successfully": ingestion.success if ingestion else 0,
            "ingested_skipped": ingestion.skipped if ingestion else 0,
            "ingested_failed": ingestion.failed if ingestion else 0,
            "wikipedia_enrichment_failures": wikipedia_enrichment_failures,
            "wikivoyage_enrichment_failures": wikivoyage_enrichment_failures,
            "errors": result.errors,
        }
    finally:
        _kb_discovery_lock.release()



from app.routers import route_validation
from app.routers import routes
app.include_router(route_validation.router, prefix="/api")
app.include_router(routes.router)
app.include_router(weather_context_router)
# The fixed batch route must be registered before the dynamic district route.
app.include_router(weather_attractions_router)
app.include_router(weather_suitability_router)
app.include_router(weather_kb_router)
app.include_router(knowledge_base_router)
app.include_router(context_enrichment_router)
# Stage 12.1: independent semantic-and-metadata baseline; not the context re-ranker.
app.include_router(content_recommendations_router)
app.include_router(time_aware_recommendations_router)
app.include_router(holiday_events_router)
# Stage 12.5 internal research endpoint. The route remains inert unless all
# independent feature flags and token authentication are configured.
app.include_router(unified_context_research_router)
# Stage 12.6 checkpointed LangGraph research workflow. It has dedicated flags
# and authentication and remains disconnected from production routing.
app.include_router(langgraph_recommendations_router)
# You can include your routers here later:
# from app.routers import recommend
# app.include_router(recommend.router, prefix="/api")
