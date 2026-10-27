# API Reference

The live OpenAPI document exposed 34 operations on 2026-10-21 (B). Principal groups:

| Group | Operations |
|---|---|
| health/internal | `GET /health`; protected KB discovery/refresh POSTs |
| knowledge base | status, attractions, nearby, detail, categories, districts, sources, quality, semantic search |
| baseline recommendations | content-based, context-enrich, time-aware |
| research | unified context POST; LangGraph context POST |
| weather | context, forecasts/status, suitability, batch, attraction weather |
| holiday/event | holidays, Poya, context/evaluate/score, events/upcoming/detail/matches |
| routes | Dijkstra and validation |

Research unified endpoint: `POST /api/v1/research/recommendations/context-aware`, header `X-Research-Token`. It needs API + engine + experimental reranking flags. Graph endpoint: `POST /api/v1/research/agents/context-aware`, headers `X-Research-Token` and `X-Research-Owner`; input includes `session_id`, natural-language `message`, configuration and limits. It can return `CLARIFICATION_REQUIRED` for a resumable session.

Common responses: 401 bad/missing token, 400 missing owner, 403 session ownership mismatch, 503 disabled/misconfigured research service, 504 graph timeout. Pydantic validates request constraints; internal KB operations also use locks to prevent overlapping runs.

Canonical machine-readable inventory: `data/reports/component1_complete_audit/component1_api_inventory.json`. Runtime truth can be inspected at `http://localhost:8000/openapi.json`.

