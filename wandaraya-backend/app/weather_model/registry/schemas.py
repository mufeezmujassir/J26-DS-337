"""Serializable schemas for the manual weather-model decision registry."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ApprovalStatus = Literal["pending_review", "approved", "rejected"]
ModelName = Literal["monthly_climatology", "seasonal_naive", "prophet"]


class ApprovalEvent(BaseModel):
    """Append-only record of a registry decision or evidence invalidation."""

    event_id: str
    occurred_at: datetime
    action: Literal["registry_created", "approved", "rejected", "evidence_changed", "artifact_changed", "artifact_registered"]
    district_id: int
    target: str
    reviewer_id: str | None = None
    reason: str
    evidence_fingerprint: str
    details: dict[str, Any] = Field(default_factory=dict)


class RegistryEntry(BaseModel):
    district_id: int
    target: str
    recommended_model: ModelName | None = None
    selected_model: ModelName | None = None
    evidence_status: Literal["eligible_for_review", "limited_evidence", "insufficient_evidence"]
    review_flags: list[str] = Field(default_factory=list)
    metrics_by_model: dict[str, dict[str, Any]] = Field(default_factory=dict)
    validation_report_path: str
    validation_evidence: dict[str, Any]
    evidence_fingerprint: str
    approval_status: ApprovalStatus = "pending_review"
    production_approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_reason: str | None = None
    resolved_review_flags: dict[str, str] = Field(default_factory=dict)
    model_version: str | None = None
    artifact_path: str | None = None
    candidate_artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)


class WeatherModelRegistry(BaseModel):
    schema_version: int = 1
    generated_at: datetime
    validation_report_path: str
    entries: list[RegistryEntry]
    audit_events: list[ApprovalEvent] = Field(default_factory=list)
    production_approved: bool = False


class ApprovalRequest(BaseModel):
    reviewer_id: str
    selected_model: ModelName
    justification: str
    resolved_review_flags: dict[str, str] = Field(default_factory=dict)

