"""Swagger contracts for read-only Tourism Knowledge Base access."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseAttractionSummary(BaseModel):
    id: int
    name: str
    district_id: int | None = None
    district: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    rating: float | None = None
    categories: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)


class NearbyAttraction(KnowledgeBaseAttractionSummary):
    distance_km: float


class KnowledgeBaseCategory(BaseModel):
    id: int
    name: str
    description: str | None = None
    active_attraction_count: int


class KnowledgeBaseDistrict(BaseModel):
    id: int
    name: str
    province: str
    latitude: float | None = None
    longitude: float | None = None
    active_attraction_count: int


class KnowledgeBaseSourceCoverage(BaseModel):
    id: int
    name: str
    source_type: str
    active: bool
    enrichment_descriptions: int


class KnowledgeBaseDescription(BaseModel):
    title: str | None = None
    description: str | None = None
    source: str | None = None
    source_url: str | None = None
    language: str | None = None


class KnowledgeBaseAttractionDetail(KnowledgeBaseAttractionSummary):
    address: str | None = None
    google_place_id: str | None = None
    website_url: str | None = None
    description: str | None = None
    is_active: bool
    updated_at: datetime | None = None
    enrichments: list[KnowledgeBaseDescription] = Field(default_factory=list)


class SemanticSearchResult(KnowledgeBaseAttractionSummary):
    semantic_score: float


class KnowledgeBaseStatus(BaseModel):
    active_attractions: int
    mapped_attractions: int
    categories: int
    activities: int
    enrichment_descriptions: int
    embedding_model: str
    embedding_dimension: int
    qdrant_collection: str
    qdrant_collection_exists: bool
    qdrant_points: int | None = None


class KnowledgeBaseQualityReport(BaseModel):
    active_attractions: int
    missing_coordinates: int
    missing_district: int
    without_category: int
    without_activity: int
    without_enrichment: int
    duplicate_google_place_ids: int
