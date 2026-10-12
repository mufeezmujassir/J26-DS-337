"""Registry and artifact integrity checks for production model forecasts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.weather_model.registry.registry_manager import RegistryManager
from app.weather_model.training.candidate_artifacts import load_candidate_artifact


@dataclass(frozen=True)
class VerifiedArtifact:
    district_id: int
    target: str
    model_name: str
    model_version: str
    manifest: dict[str, Any]
    payload: bytes
    evidence_status: str


class ArtifactVerifier:
    """Verify an explicitly approved registry selection before loading it."""

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path

    def verify(self, district_id: int, target: str) -> VerifiedArtifact:
        registry = RegistryManager(self.registry_path).load()
        if registry is None:
            raise ValueError("weather_model_registry_missing")
        entry = next(
            (item for item in registry.entries if item.district_id == district_id and item.target == target),
            None,
        )
        if entry is None:
            raise ValueError("registry_series_missing")
        if not entry.production_approved or entry.approval_status != "approved":
            raise ValueError("no_production_approved_model")
        if not entry.selected_model:
            raise ValueError("approved_entry_has_no_selected_model")
        reference = entry.candidate_artifacts.get(entry.selected_model)
        if not reference:
            raise ValueError("approved_model_artifact_missing")
        if reference.get("model_version") != entry.model_version:
            raise ValueError("registry_model_version_mismatch")
        artifact_path = Path(reference.get("artifact_path", ""))
        manifest_path = artifact_path.parent / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("artifact_manifest_missing")
        try:
            manifest, payload = load_candidate_artifact(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"artifact_integrity_failed: {exc}") from exc
        if manifest.get("artifact_version") != entry.model_version:
            raise ValueError("artifact_version_mismatch")
        if manifest.get("registry_evidence_fingerprint") != entry.evidence_fingerprint:
            raise ValueError("artifact_evidence_invalidated")
        if manifest.get("target") != target or manifest.get("district_id") != district_id:
            raise ValueError("artifact_series_mismatch")
        if manifest.get("model_name") != entry.selected_model:
            raise ValueError("artifact_model_mismatch")
        return VerifiedArtifact(
            district_id=district_id,
            target=target,
            model_name=entry.selected_model,
            model_version=entry.model_version or "",
            manifest=manifest,
            payload=payload,
            evidence_status=entry.evidence_status,
        )


def is_forecast_after_training_cutoff(artifact: VerifiedArtifact, forecast_month: date) -> bool:
    cutoff = date.fromisoformat(artifact.manifest["provenance"]["training_cutoff"])
    return forecast_month > cutoff
