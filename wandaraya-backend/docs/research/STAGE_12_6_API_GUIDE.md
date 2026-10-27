# Stage 12.6 Research API Guide

Endpoint: `POST /api/v1/research/agents/context-aware`

Required headers are `X-Research-Token` and `X-Research-Owner`. Configure a dedicated token of at least 32 characters. The route never falls back to the Airflow token.

```json
{
  "session_id": "research-session-001",
  "message": "Recommend cultural attractions near Kandy tomorrow morning",
  "reranker_configuration": "R3_WEATHER_SEASONALITY_REDUNDANCY_CONTROLLED",
  "candidate_limit": 20,
  "result_limit": 5
}
```

Enable only in a research environment:

```ini
ENABLE_LANGGRAPH_RECOMMENDATION_ENGINE=true
ENABLE_LANGGRAPH_RESEARCH_API=true
LANGGRAPH_RESEARCH_API_TOKEN=<dedicated-32-plus-character-token>
```

All new flags default to false. A missing-field response has status `CLARIFICATION_REQUIRED`; submit the answer with the same session and owner to resume. Responses include parsed intent, node/tool audit trails, candidates with source evidence, separate original/experimental/production orders, warnings, errors, and the fixed group-emotion deferred status.
