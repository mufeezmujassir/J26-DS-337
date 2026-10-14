"""Read-only, Swagger-visible Tourism Knowledge Base endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from qdrant_client import QdrantClient
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer
from app.knowledge_base.retrieval.semantic_retriever import SemanticAttractionRetriever
from app.models.activities import Activity
from app.models.attraction import Attraction
from app.models.attraction_activities import AttractionActivity
from app.models.attraction_categories import AttractionCategory
from app.models.attraction_descriptions import AttractionDescription
from app.models.categories import Category
from app.models.data_sources import DataSource
from app.models.district import District
from app.schemas.knowledge_base import (
    KnowledgeBaseAttractionDetail,
    KnowledgeBaseAttractionSummary,
    KnowledgeBaseCategory,
    KnowledgeBaseDescription,
    KnowledgeBaseDistrict,
    KnowledgeBaseQualityReport,
    KnowledgeBaseStatus,
    KnowledgeBaseSourceCoverage,
    NearbyAttraction,
    SemanticSearchResult,
)


router = APIRouter(prefix="/api/v1/knowledge-base", tags=["Tourism Knowledge Base"])


async def _names(db: AsyncSession, attraction_id: int) -> tuple[list[str], list[str]]:
    categories = list((await db.scalars(
        select(Category.name).join(AttractionCategory).where(AttractionCategory.attraction_id == attraction_id)
    )).all())
    activities = list((await db.scalars(
        select(Activity.name).join(AttractionActivity).where(AttractionActivity.attraction_id == attraction_id)
    )).all())
    return sorted(categories), sorted(activities)


async def _summary(db: AsyncSession, attraction: Attraction, district_name: str | None = None) -> KnowledgeBaseAttractionSummary:
    categories, activities = await _names(db, attraction.id)
    return KnowledgeBaseAttractionSummary(
        id=attraction.id, name=attraction.name, district_id=attraction.district_id, district=district_name,
        city=attraction.city, latitude=attraction.latitude, longitude=attraction.longitude,
        rating=attraction.rating, categories=categories, activities=activities,
    )


@router.get("/status", response_model=KnowledgeBaseStatus, summary="Get Knowledge Base indexing status")
async def knowledge_base_status(db: AsyncSession = Depends(get_db)) -> KnowledgeBaseStatus:
    """Show current database and Qdrant counts without generating embeddings."""
    active = await db.scalar(select(func.count()).select_from(Attraction).where(Attraction.is_active.is_(True)))
    mapped = await db.scalar(select(func.count()).select_from(Attraction).where(
        Attraction.is_active.is_(True), Attraction.district_id.is_not(None)
    ))
    categories = await db.scalar(select(func.count()).select_from(Category).where(Category.is_active.is_(True)))
    activities = await db.scalar(select(func.count()).select_from(Activity).where(Activity.is_active.is_(True)))
    descriptions = await db.scalar(select(func.count()).select_from(AttractionDescription).where(AttractionDescription.is_active.is_(True)))
    collection = AttractionQdrantIndexer.COLLECTION_NAME
    exists, points = False, None
    try:
        client = QdrantClient(url=settings.QDRANT_URL)
        exists = client.collection_exists(collection)
        points = client.count(collection, exact=True).count if exists else 0
    except Exception:
        # Database facts remain usable even if the vector service is temporarily unavailable.
        pass
    return KnowledgeBaseStatus(
        active_attractions=int(active or 0), mapped_attractions=int(mapped or 0),
        categories=int(categories or 0), activities=int(activities or 0),
        enrichment_descriptions=int(descriptions or 0), embedding_model=AttractionEmbeddingService.MODEL_NAME,
        embedding_dimension=AttractionEmbeddingService.EXPECTED_DIMENSION, qdrant_collection=collection,
        qdrant_collection_exists=exists, qdrant_points=points,
    )


@router.get("/attractions", response_model=list[KnowledgeBaseAttractionSummary], summary="List active attractions")
async def list_attractions(
    district_id: int | None = Query(default=None, gt=0),
    category: str | None = Query(default=None, min_length=1),
    activity: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeBaseAttractionSummary]:
    """Filter structured, active attractions; no external provider is called."""
    statement = select(Attraction, District.name).outerjoin(District, District.id == Attraction.district_id).where(
        Attraction.is_active.is_(True)
    )
    if district_id is not None:
        statement = statement.where(Attraction.district_id == district_id)
    if category:
        statement = statement.join(AttractionCategory).join(Category).where(Category.name.ilike(category.strip()))
    if activity:
        statement = statement.join(AttractionActivity).join(Activity).where(Activity.name.ilike(activity.strip()))
    # Association tables enforce one mapping per attraction/category or
    # attraction/activity, so this query does not need SQL DISTINCT. PostgreSQL
    # cannot compare the attraction JSON columns selected by ORM DISTINCT.
    rows = (await db.execute(statement.order_by(Attraction.name).limit(limit))).all()
    return [await _summary(db, attraction, district) for attraction, district in rows]


@router.get("/attractions/nearby", response_model=list[NearbyAttraction], summary="Find active attractions near coordinates")
async def nearby_attractions(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=20, gt=0, le=200),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[NearbyAttraction]:
    """Geographic radius filter over stored coordinates; it never calls a provider."""
    # Haversine great-circle distance. Attractions do not currently have a
    # PostGIS point column, so this uses their verified latitude/longitude.
    distance = 6371.0088 * func.acos(func.least(1.0, func.greatest(-1.0,
        func.cos(func.radians(latitude)) * func.cos(func.radians(Attraction.latitude)) *
        func.cos(func.radians(Attraction.longitude) - func.radians(longitude)) +
        func.sin(func.radians(latitude)) * func.sin(func.radians(Attraction.latitude))
    )))
    rows = (await db.execute(
        select(Attraction, District.name, distance.label("distance_km"))
        .outerjoin(District, District.id == Attraction.district_id)
        .where(Attraction.is_active.is_(True), Attraction.latitude.is_not(None), Attraction.longitude.is_not(None))
        .where(distance <= radius_km).order_by(distance).limit(limit)
    )).all()
    results = []
    for attraction, district, distance_km in rows:
        summary = await _summary(db, attraction, district)
        results.append(NearbyAttraction(**summary.model_dump(), distance_km=round(float(distance_km), 3)))
    return results


@router.get("/attractions/{attraction_id}", response_model=KnowledgeBaseAttractionDetail, summary="Get an attraction and enrichments")
async def get_attraction(attraction_id: int, db: AsyncSession = Depends(get_db)) -> KnowledgeBaseAttractionDetail:
    row = (await db.execute(
        select(Attraction, District.name).outerjoin(District, District.id == Attraction.district_id).where(
            Attraction.id == attraction_id, Attraction.is_active.is_(True)
        )
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Active attraction not found.")
    attraction, district = row
    summary = await _summary(db, attraction, district)
    enrichments = (await db.execute(
        select(AttractionDescription, DataSource.name).outerjoin(DataSource, DataSource.id == AttractionDescription.source_id).where(
            AttractionDescription.attraction_id == attraction.id, AttractionDescription.is_active.is_(True)
        ).order_by(AttractionDescription.created_at.desc())
    )).all()
    return KnowledgeBaseAttractionDetail(
        **summary.model_dump(), address=attraction.address, google_place_id=attraction.google_place_id,
        website_url=attraction.website_url, description=attraction.description, is_active=attraction.is_active,
        updated_at=attraction.updated_at,
        enrichments=[KnowledgeBaseDescription(
            title=item.title, description=item.description, source=source, source_url=item.source_url,
            language=item.language,
        ) for item, source in enrichments],
    )


@router.get("/categories", response_model=list[KnowledgeBaseCategory], summary="List attraction categories and coverage")
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[KnowledgeBaseCategory]:
    rows = (await db.execute(
        select(Category, func.count(AttractionCategory.attraction_id).label("mapped"))
        .outerjoin(AttractionCategory, AttractionCategory.category_id == Category.id)
        .group_by(Category.id).order_by(Category.name)
    )).all()
    return [KnowledgeBaseCategory(
        id=category.id, name=category.name, description=category.description,
        active_attraction_count=int(mapped),
    ) for category, mapped in rows]


@router.get("/districts", response_model=list[KnowledgeBaseDistrict], summary="List districts and attraction coverage")
async def list_districts(db: AsyncSession = Depends(get_db)) -> list[KnowledgeBaseDistrict]:
    rows = (await db.execute(
        select(District, func.count(Attraction.id).label("mapped"))
        .outerjoin(Attraction, and_(Attraction.district_id == District.id, Attraction.is_active.is_(True)))
        .group_by(District.id).order_by(District.name)
    )).all()
    return [KnowledgeBaseDistrict(
        id=district.id, name=district.name, province=district.province, latitude=district.latitude,
        longitude=district.longitude, active_attraction_count=int(mapped),
    ) for district, mapped in rows]


@router.get("/sources", response_model=list[KnowledgeBaseSourceCoverage], summary="List source and enrichment coverage")
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[KnowledgeBaseSourceCoverage]:
    rows = (await db.execute(
        select(DataSource, func.count(AttractionDescription.id).label("enrichments"))
        .outerjoin(AttractionDescription, AttractionDescription.source_id == DataSource.id)
        .group_by(DataSource.id).order_by(DataSource.name)
    )).all()
    return [KnowledgeBaseSourceCoverage(
        id=source.id, name=source.name, source_type=source.source_type, active=source.is_active,
        enrichment_descriptions=int(enrichments),
    ) for source, enrichments in rows]


@router.get("/quality", response_model=KnowledgeBaseQualityReport, summary="Get Knowledge Base data-quality coverage")
async def quality_report(db: AsyncSession = Depends(get_db)) -> KnowledgeBaseQualityReport:
    """Read-only coverage report; it does not repair, import, or delete data."""
    active_filter = Attraction.is_active.is_(True)
    active = await db.scalar(select(func.count()).select_from(Attraction).where(active_filter))
    missing_coordinates = await db.scalar(select(func.count()).select_from(Attraction).where(
        active_filter, (Attraction.latitude.is_(None) | Attraction.longitude.is_(None))
    ))
    missing_district = await db.scalar(select(func.count()).select_from(Attraction).where(
        active_filter, Attraction.district_id.is_(None)
    ))
    categorized = select(AttractionCategory.attraction_id).distinct()
    active_with_activity = select(AttractionActivity.attraction_id).distinct()
    enriched = select(AttractionDescription.attraction_id).where(AttractionDescription.is_active.is_(True)).distinct()
    without_category = await db.scalar(select(func.count()).select_from(Attraction).where(active_filter, Attraction.id.not_in(categorized)))
    without_activity = await db.scalar(select(func.count()).select_from(Attraction).where(active_filter, Attraction.id.not_in(active_with_activity)))
    without_enrichment = await db.scalar(select(func.count()).select_from(Attraction).where(active_filter, Attraction.id.not_in(enriched)))
    duplicate_groups = await db.scalar(select(func.count()).select_from(
        select(Attraction.google_place_id).where(Attraction.google_place_id.is_not(None)).group_by(
            Attraction.google_place_id
        ).having(func.count(Attraction.id) > 1).subquery()
    ))
    return KnowledgeBaseQualityReport(
        active_attractions=int(active or 0), missing_coordinates=int(missing_coordinates or 0),
        missing_district=int(missing_district or 0), without_category=int(without_category or 0),
        without_activity=int(without_activity or 0), without_enrichment=int(without_enrichment or 0),
        duplicate_google_place_ids=int(duplicate_groups or 0),
    )


@router.get("/semantic-search", response_model=list[SemanticSearchResult], summary="Semantic attraction candidate retrieval")
async def semantic_search(
    query: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[SemanticSearchResult]:
    """Embed a natural-language query, search Qdrant, then hydrate active PostgreSQL records."""
    try:
        candidates = await SemanticAttractionRetriever().search(db=db, query=query, limit=limit)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Semantic search is unavailable: {exc}") from exc
    results = []
    for candidate in candidates:
        attraction = await db.get(Attraction, candidate.attraction_id)
        if attraction is None:
            continue
        summary = await _summary(db, attraction)
        results.append(SemanticSearchResult(**summary.model_dump(), semantic_score=candidate.score))
    return results
