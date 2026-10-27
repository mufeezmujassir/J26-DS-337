from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.recommendation.unified_context.schemas import RerankerConfiguration


class AgenticRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,79}$")
    message: str = Field(min_length=2, max_length=2000)
    reranker_configuration: RerankerConfiguration = RerankerConfiguration.R3
    candidate_limit: int = Field(default=20, ge=1, le=50)
    result_limit: int = Field(default=5, ge=1, le=20)

    def model_post_init(self, __context) -> None:
        if self.result_limit > self.candidate_limit:
            raise ValueError("result_limit cannot exceed candidate_limit")
