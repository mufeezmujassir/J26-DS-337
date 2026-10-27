# Live Demonstration Guide

## Preparation

Run `docker compose ps`, `/health`, and KB status first. Keep production flags false. Use research tokens only in local shell variables and never project them.

1. **Knowledge base** — call `/api/v1/knowledge-base/status`, attractions/categories/districts, and explain the verified 6,120/25/18/50 snapshot. Show the API-reported Qdrant collection rather than legacy port 6333.
2. **Semantic retrieval** — `Invoke-RestMethod 'http://localhost:8000/api/v1/knowledge-base/semantic-search?query=quiet%20beach%20for%20sunset&limit=5'`. Point out scores and preserved ordering; do not promise the exact names in advance.
3. **Weather** — request a district/date supported by `/api/v1/weather/context/{district_id}`; show source, resolution and missing evidence. Say that climatology is not a day forecast.
4. **Time** — POST the same candidates to `/api/v1/recommendations/time-aware` at an open and closed time. Explain 1/.5/0/null.
5. **Holiday/Poya** — list `/api/v1/calendar/poya-days`, choose an actual returned date, then evaluate context. Explain that relevance does not prove closure/crowds.
6. **Seasonality** — use an attraction/activity mapping known from the DB and compare a mapped and unmapped case; unavailable is a safe outcome.
7. **Unified R0-R3** — on the protected research endpoint, hold query/candidates/date constant and change only configuration. Compare original rank, experimental rank, movement, contributions and unavailable evidence.
8. **LangGraph** — send an incomplete message to show clarification, then resume the same `session_id`/owner. Next send a complete destination/activity/date request and show nodes/tool calls.
9. **Failure handling** — choose missing optional evidence; show abstention without a fabricated zero. Do not deliberately stop infrastructure during a presentation.
10. **Evaluation** — open Stage 12.4F/G and Stage 12.6 reports; separate passed tests/pilot reliability from recommendation accuracy.

Panel script: “The semantic baseline produces candidates; four independently traceable context adapters provide evidence; R0-R3 are experimental; LangGraph coordinates clarification and verified tools; group emotion and production switching are intentionally disabled.”

If a research endpoint returns 503, confirm its isolated flags and container environment. If 401, verify the local header without displaying it. If Qdrant direct inspection disagrees, use the API container’s configured replacement service.

