"""Offline source-governance contracts for future timing acquisition.

This package deliberately contains no provider client, persistence code, or
network access.  It makes later source collection reviewable before it is
authorised.
"""

from app.time_context.governance.reconciliation import reconcile_timing_evidence
from app.time_context.governance.schemas import TimingSourceEvidence

__all__ = ["TimingSourceEvidence", "reconcile_timing_evidence"]
