# Component 1 Flutter API Mapping

All mappings below were verified from backend route and Pydantic source, not inferred from the reference images.

| Flutter capability | Method and route | Authorization | Main response use |
|---|---|---|---|
| Connection check | `GET /health` | None | Settings connection state |
| Research statistics | `GET /api/v1/knowledge-base/status` | None | Attraction/category/activity counts, embedding and Qdrant status |
| Discover listing | `GET /api/v1/knowledge-base/attractions` | None | Real attraction cards |
| Attraction detail | `GET /api/v1/knowledge-base/attractions/{id}` | None | Verified descriptive and practical fields |
| Category interests | `GET /api/v1/knowledge-base/categories` | None | Discover and preference chips |
| District selector | `GET /api/v1/knowledge-base/districts` | None | Destination selection |
| Semantic search | `GET /api/v1/knowledge-base/semantic-search?query=&limit=` | None | Debounced live candidates and semantic scores |
| Context recommendation | `POST /api/v1/research/recommendations/context-aware` | `X-Research-Token` | R0–R3 ranks, scores, evidence, explanation and limitations |
| LangGraph assistant | `POST /api/v1/research/agents/context-aware` | `X-Research-Token`, `X-Research-Owner` | Clarification, session continuity, recommendations, node names and warnings |

## Data integrity decisions

- Context scores and confidence remain nullable. Unavailable evidence is shown as unavailable, never `0%`.
- Semantic similarity is labelled as a score, never as calibrated probability or accuracy.
- The four active evidence dimensions are weather, time of day, holiday/Poya/event, and historical seasonality.
- Group Emotion is excluded from requests and appears only as “Future Integration” in Research Insights.
- The attraction response has no verified image URL, opening-hours, price, or facility contract. The UI does not fabricate them.
- No verified endpoint lists the activity taxonomy. Categories are sent as interests and requested activities remain empty unless a future verified route supplies values.
- Pipeline cards describe verified architecture. They do not imply live per-node execution or invented timing.

## Error mapping

The Dio client maps validation failures (400/422), authorization failures (401/403), not found (404), disabled/unavailable services (503), timeout, connection refusal, and malformed payloads into readable UI states with retry where appropriate. Tokens are read from secure runtime storage and are never logged or compiled into the APK.
