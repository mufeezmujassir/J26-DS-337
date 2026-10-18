from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.time_context.governance.adapters import AdapterResult
from app.time_context.governance.policy import TimingGovernancePolicy
from app.time_context.governance.reconciliation import reconcile_timing_evidence
from app.time_context.governance.schemas import ReconciliationDecision, TimingReconciliationResult, TimingSourceEvidence


class OfflineAcquisitionAssessment(BaseModel):
    adapter_results: list[AdapterResult] = Field(default_factory=list)
    reconciliation: TimingReconciliationResult | None = None
    persistence_eligible: bool = False
    persistence_reason: str = "offline_gate_never_persists"


def assess_offline_acquisition(results: list[AdapterResult], policy: TimingGovernancePolicy | None, *, on_date: date | None = None) -> OfflineAcquisitionAssessment:
    evidence = [result.evidence for result in results if result.evidence is not None]
    reconciliation = reconcile_timing_evidence(evidence, policy, on_date=on_date) if evidence else None
    # Gate 1 always keeps persistence disabled, even if a future policy would
    # permit it. Persistence is a separately approved later stage.
    return OfflineAcquisitionAssessment(adapter_results=results, reconciliation=reconciliation, persistence_eligible=False)
