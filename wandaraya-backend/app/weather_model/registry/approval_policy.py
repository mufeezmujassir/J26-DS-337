"""Conservative human-approval policy for registry entries."""

from __future__ import annotations

from app.weather_model.registry.schemas import ApprovalRequest, RegistryEntry


def approval_blockers(entry: RegistryEntry, request: ApprovalRequest) -> list[str]:
    """Return every unmet manual-approval condition without mutating state."""
    blockers: list[str] = []
    if entry.approval_status == "approved":
        blockers.append("This series is already approved; duplicate approval is blocked.")
    if entry.evidence_status == "insufficient_evidence":
        blockers.append("Insufficient evidence cannot be approved under the normal policy.")
    paired = entry.validation_evidence.get("paired_prediction_validation", {})
    if not paired.get("paired_observed_targets_valid", False):
        blockers.append("The selected model lacks valid paired comparison evidence.")
    selected_metrics = entry.metrics_by_model.get(request.selected_model, {})
    if selected_metrics.get("mae") is None:
        blockers.append("The selected model has no valid MAE evidence for this series.")
    unresolved = [
        flag
        for flag in entry.review_flags
        if not request.resolved_review_flags.get(flag, "").strip()
    ]
    if unresolved:
        blockers.append(
            "Unresolved review flags require documented resolution: "
            + ", ".join(unresolved)
        )
    if not request.reviewer_id.strip():
        blockers.append("A reviewer identifier is required.")
    if not request.justification.strip():
        blockers.append("An approval justification is required.")
    return blockers

