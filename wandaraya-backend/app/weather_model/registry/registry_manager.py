"""Atomic JSON registry builder and explicit decision manager."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.weather_model.registry.approval_policy import approval_blockers
from app.weather_model.registry.schemas import (
    ApprovalEvent,
    ApprovalRequest,
    RegistryEntry,
    WeatherModelRegistry,
)


VALIDATION_REPORT_PATH = "data/weather/reports/backtesting/model_selection_validation.json"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(value: object) -> str:
    """Stable content fingerprint used to invalidate stale human decisions."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def entry_key(entry: RegistryEntry) -> tuple[int, str]:
    return entry.district_id, entry.target


def _event(
    action: str,
    entry: RegistryEntry,
    *,
    reason: str,
    reviewer_id: str | None = None,
    details: dict | None = None,
) -> ApprovalEvent:
    return ApprovalEvent(
        event_id=str(uuid4()),
        occurred_at=utc_now(),
        action=action,
        district_id=entry.district_id,
        target=entry.target,
        reviewer_id=reviewer_id,
        reason=reason,
        evidence_fingerprint=entry.evidence_fingerprint,
        details=details or {},
    )


class RegistryManager:
    """Manage explicit review decisions while preserving audit history."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> WeatherModelRegistry | None:
        if not self.path.exists():
            return None
        return WeatherModelRegistry.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, registry: WeatherModelRegistry) -> None:
        """Atomically replace the registry file after a complete validation."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = registry.model_dump_json(indent=2)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)

    def build_from_validation(
        self,
        validation: dict,
        *,
        validation_report_path: str = VALIDATION_REPORT_PATH,
    ) -> WeatherModelRegistry:
        """Import validation evidence while retaining only still-valid decisions."""
        prior = self.load()
        prior_entries = {entry_key(item): item for item in prior.entries} if prior else {}
        audit_events = list(prior.audit_events) if prior else []
        entries: list[RegistryEntry] = []

        for source in sorted(validation.get("series", []), key=lambda item: (item["district_id"], item["target"])):
            source_fingerprint = fingerprint(source)
            key = int(source["district_id"]), str(source["target"])
            previous = prior_entries.get(key)
            base = RegistryEntry(
                district_id=key[0],
                target=key[1],
                recommended_model=source.get("provisional_candidate"),
                selected_model=None,
                evidence_status=source["evidence_status"],
                review_flags=list(source.get("review_flags", [])),
                metrics_by_model=dict(source.get("model_metrics", {})),
                validation_report_path=validation_report_path,
                validation_evidence=dict(source),
                evidence_fingerprint=source_fingerprint,
            )
            if previous is None:
                audit_events.append(
                    _event("registry_created", base, reason="Imported validation evidence for manual review.")
                )
            elif previous.evidence_fingerprint == source_fingerprint:
                # Preserve manual review state only when exactly the same
                # evidence was used for the decision.
                base = base.model_copy(
                    update={
                        "selected_model": previous.selected_model,
                        "approval_status": previous.approval_status,
                        "production_approved": previous.production_approved,
                        "approved_by": previous.approved_by,
                        "approved_at": previous.approved_at,
                        "approval_reason": previous.approval_reason,
                        "resolved_review_flags": previous.resolved_review_flags,
                        "model_version": previous.model_version,
                        "artifact_path": previous.artifact_path,
                        "candidate_artifacts": previous.candidate_artifacts,
                    }
                )
            else:
                # Never carry an approval or artifact forward after material
                # validation evidence changes.
                audit_events.append(
                    _event(
                        "evidence_changed",
                        base,
                        reason="Validation evidence changed; prior decision requires revalidation.",
                        details={"previous_evidence_fingerprint": previous.evidence_fingerprint},
                    )
                )
            entries.append(base)

        return WeatherModelRegistry(
            generated_at=utc_now(),
            validation_report_path=validation_report_path,
            entries=entries,
            audit_events=audit_events,
            production_approved=any(entry.production_approved for entry in entries),
        )

    def rebuild_from_validation_file(self, validation_path: Path) -> WeatherModelRegistry:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        registry = self.build_from_validation(
            validation,
            validation_report_path=str(validation_path),
        )
        self.save(registry)
        return registry

    @staticmethod
    def _find(registry: WeatherModelRegistry, district_id: int, target: str) -> RegistryEntry:
        for entry in registry.entries:
            if entry.district_id == district_id and entry.target == target:
                return entry
        raise KeyError(f"No registry series for district={district_id}, target={target}")

    def approve(
        self,
        registry: WeatherModelRegistry,
        district_id: int,
        target: str,
        request: ApprovalRequest,
    ) -> WeatherModelRegistry:
        entry = self._find(registry, district_id, target)
        blockers = approval_blockers(entry, request)
        if blockers:
            raise ValueError("Approval blocked: " + " ".join(blockers))

        updated = entry.model_copy(
            update={
                "selected_model": request.selected_model,
                "approval_status": "approved",
                "production_approved": True,
                "approved_by": request.reviewer_id.strip(),
                "approved_at": utc_now(),
                "approval_reason": request.justification.strip(),
                "resolved_review_flags": {
                    key: value.strip() for key, value in request.resolved_review_flags.items()
                },
            }
        )
        registry.entries[registry.entries.index(entry)] = updated
        registry.audit_events.append(
            _event(
                "approved",
                updated,
                reviewer_id=updated.approved_by,
                reason=updated.approval_reason or "Manual approval",
                details={"selected_model": updated.selected_model},
            )
        )
        registry.production_approved = any(item.production_approved for item in registry.entries)
        return registry

    def reject(
        self,
        registry: WeatherModelRegistry,
        district_id: int,
        target: str,
        *,
        reviewer_id: str,
        reason: str,
    ) -> WeatherModelRegistry:
        if not reviewer_id.strip() or not reason.strip():
            raise ValueError("Rejection requires a reviewer identifier and reason.")
        entry = self._find(registry, district_id, target)
        updated = entry.model_copy(
            update={
                "selected_model": None,
                "approval_status": "rejected",
                "production_approved": False,
                "approved_by": reviewer_id.strip(),
                "approved_at": utc_now(),
                "approval_reason": reason.strip(),
            }
        )
        registry.entries[registry.entries.index(entry)] = updated
        registry.audit_events.append(
            _event("rejected", updated, reviewer_id=updated.approved_by, reason=updated.approval_reason or "Manual rejection")
        )
        registry.production_approved = any(item.production_approved for item in registry.entries)
        return registry

    def record_artifact_change(
        self,
        registry: WeatherModelRegistry,
        district_id: int,
        target: str,
        *,
        model_version: str | None,
        artifact_path: str | None,
        reason: str,
    ) -> WeatherModelRegistry:
        """Invalidate any decision when training output changes materially."""
        entry = self._find(registry, district_id, target)
        updated = entry.model_copy(
            update={
                "approval_status": "pending_review",
                "production_approved": False,
                "selected_model": None,
                "approved_by": None,
                "approved_at": None,
                "approval_reason": None,
                "resolved_review_flags": {},
                "model_version": model_version,
                "artifact_path": artifact_path,
            }
        )
        registry.entries[registry.entries.index(entry)] = updated
        registry.audit_events.append(
            _event("artifact_changed", updated, reason=reason))
        registry.production_approved = any(item.production_approved for item in registry.entries)
        return registry

    def register_candidate_artifact(
        self,
        registry: WeatherModelRegistry,
        district_id: int,
        target: str,
        *,
        model_name: str,
        model_version: str,
        artifact_path: str,
        checksum_sha256: str,
    ) -> WeatherModelRegistry:
        """Attach a newly trained candidate and require fresh manual review.

        An artifact is never an approval.  Replacing/adding one invalidates a
        previous selection because its binary/model state is now different.
        """
        entry = self._find(registry, district_id, target)
        artifacts = dict(entry.candidate_artifacts)
        artifacts[model_name] = {
            "model_version": model_version,
            "artifact_path": artifact_path,
            "checksum_sha256": checksum_sha256,
            "production_approved": False,
        }
        updated = entry.model_copy(
            update={
                "approval_status": "pending_review",
                "production_approved": False,
                "selected_model": None,
                "approved_by": None,
                "approved_at": None,
                "approval_reason": None,
                "resolved_review_flags": {},
                "model_version": model_version if entry.recommended_model == model_name else entry.model_version,
                "artifact_path": artifact_path if entry.recommended_model == model_name else entry.artifact_path,
                "candidate_artifacts": artifacts,
            }
        )
        registry.entries[registry.entries.index(entry)] = updated
        registry.audit_events.append(
            _event(
                "artifact_registered",
                updated,
                reason="Trained candidate registered; manual approval remains required.",
                details={"model_name": model_name, "model_version": model_version, "checksum_sha256": checksum_sha256},
            )
        )
        registry.production_approved = any(item.production_approved for item in registry.entries)
        return registry
