from __future__ import annotations

from app.recommendation.unified_context.schemas import (
    CandidateExplanation,
    ContextEvidence,
    EvidenceStatus,
)


def explain_candidate(evidence: dict[str, ContextEvidence]) -> CandidateExplanation:
    positive: list[str] = []
    negative: list[str] = []
    missing: list[str] = []
    sources: list[str] = []
    limitations: list[str] = []
    for dimension, item in evidence.items():
        if item.source:
            sources.append(f"{dimension}:{item.source}")
        limitations.extend(item.limitations)
        if item.status not in {EvidenceStatus.AVAILABLE, EvidenceStatus.PARTIALLY_AVAILABLE} or item.score is None:
            missing.append(dimension)
            continue
        if item.score >= 0.60:
            positive.append(f"{dimension}: {item.explanation}")
        elif item.score < 0.40:
            negative.append(f"{dimension}: {item.explanation}")
    clauses = []
    if positive:
        clauses.append(f"{len(positive)} context dimension(s) contributed positively")
    if negative:
        clauses.append(f"{len(negative)} context dimension(s) indicated unfavorable or restrictive evidence")
    if missing:
        clauses.append(f"evidence was unavailable for {', '.join(missing)}")
    if not clauses:
        clauses.append("no context score was available, so semantic relevance determined the result")
    return CandidateExplanation(
        positive_factors=positive,
        negative_factors=negative,
        missing_dimensions=missing,
        evidence_sources=sorted(set(sources)),
        limitations=sorted(set(limitations)),
        summary="; ".join(clauses) + ".",
    )
