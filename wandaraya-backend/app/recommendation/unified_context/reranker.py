from __future__ import annotations

from dataclasses import dataclass

from app.recommendation.unified_context.explainability import explain_candidate
from app.recommendation.unified_context.schemas import (
    ContextContribution,
    ContextEvidence,
    EvidenceStatus,
    RerankerConfiguration,
    UnifiedRankedCandidate,
)


@dataclass(frozen=True)
class RankingCandidate:
    attraction_id: int
    attraction_name: str
    semantic_score: float
    normalized_semantic_score: float
    semantic_rank: int
    evidence: dict[str, ContextEvidence]
    semantic_metadata: dict


class ExperimentalContextReranker:
    """Deterministic, interpretable and explicitly unvalidated re-ranker."""

    def rerank(
        self,
        candidates: list[RankingCandidate],
        configuration: RerankerConfiguration,
        semantic_alpha: float,
    ) -> list[UnifiedRankedCandidate]:
        scored: list[tuple[RankingCandidate, float, float | None, list[ContextContribution], float | None]] = []
        for candidate in candidates:
            context_score, contributions, confidence = self._context_score(candidate.evidence, configuration)
            if configuration is RerankerConfiguration.R0 or context_score is None:
                final = candidate.normalized_semantic_score
            else:
                final = semantic_alpha * candidate.normalized_semantic_score + (1 - semantic_alpha) * context_score

            # A verified closed state is a hard operational restriction.  The
            # candidate remains visible for auditability, but cannot be lifted
            # by semantic or other positive evidence.
            time_item = candidate.evidence.get("time_of_day")
            if (
                configuration is not RerankerConfiguration.R0
                and time_item
                and time_item.details.get("opening_status") == "CLOSED"
            ):
                final = 0.0
            scored.append((candidate, round(max(0.0, min(1.0, final)), 6), context_score, contributions, confidence))

        scored.sort(key=lambda row: (-row[1], row[0].semantic_rank, row[0].attraction_id))
        output: list[UnifiedRankedCandidate] = []
        for rank, (candidate, final, context_score, contributions, confidence) in enumerate(scored, 1):
            explanation = explain_candidate(candidate.evidence)
            limitations = sorted({value for item in candidate.evidence.values() for value in item.limitations})
            output.append(UnifiedRankedCandidate(
                attraction_id=candidate.attraction_id,
                attraction_name=candidate.attraction_name,
                original_semantic_score=candidate.semantic_score,
                normalized_semantic_score=candidate.normalized_semantic_score,
                original_semantic_rank=candidate.semantic_rank,
                final_experimental_context_score=final,
                experimental_rank=rank,
                rank_movement=candidate.semantic_rank - rank,
                context_score=context_score,
                evidence=candidate.evidence,
                contributions=contributions,
                evidence_availability={key: item.status for key, item in candidate.evidence.items()},
                source_provenance={
                    "semantic": candidate.semantic_metadata,
                    **{key: item.provenance for key, item in candidate.evidence.items()},
                },
                confidence=confidence,
                limitations=limitations,
                explanation=explanation,
            ))
        return output

    def _context_score(
        self, evidence: dict[str, ContextEvidence], configuration: RerankerConfiguration
    ) -> tuple[float | None, list[ContextContribution], float | None]:
        if configuration is RerankerConfiguration.R0:
            return None, [], None
        available = {
            key: item for key, item in evidence.items()
            if item.status in {EvidenceStatus.AVAILABLE, EvidenceStatus.PARTIALLY_AVAILABLE}
            and item.score is not None
        }
        if not available:
            return None, [], None

        components: list[tuple[str, float, float, EvidenceStatus]] = []
        if configuration is RerankerConfiguration.R3:
            climate = [available.pop(name) for name in ("weather", "historical_seasonality") if name in available]
            if climate:
                climate_score = sum(item.score for item in climate) / len(climate)
                components.append(("weather_seasonality_combined", climate_score, 1.0, EvidenceStatus.AVAILABLE))

        for name, item in available.items():
            if configuration is RerankerConfiguration.R2:
                if item.confidence is None or item.confidence <= 0:
                    continue
                weight = item.confidence
            else:
                weight = 1.0
            components.append((name, item.score, weight, item.status))
        if not components:
            return None, [], None
        denominator = sum(weight for _, _, weight, _ in components)
        score = sum(value * weight for _, value, weight, _ in components) / denominator
        contributions = [ContextContribution(
            dimension=name,
            score=round(value, 6),
            effective_weight=round(weight / denominator, 6),
            weighted_value=round(value * weight / denominator, 6),
            evidence_status=status,
        ) for name, value, weight, status in components]
        qualities = [item.confidence for item in evidence.values() if item.confidence is not None and item.score is not None]
        confidence = round(sum(qualities) / len(qualities), 6) if qualities else None
        return round(score, 6), contributions, confidence
