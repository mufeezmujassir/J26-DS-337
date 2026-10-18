"""Small helpers for transparent, deterministic scoring explanations."""

from __future__ import annotations

from app.weather_model.context_scoring.schemas import ScoreExplanation


def penalty(factor: str, detail: str, amount: float) -> ScoreExplanation:
    return ScoreExplanation(factor=factor, effect="penalty", detail=detail, score_delta=round(-amount, 4))


def informational(factor: str, detail: str) -> ScoreExplanation:
    return ScoreExplanation(factor=factor, effect="informational", detail=detail)
