# Component 1 Executive Summary

Audit date: 2026-10-21. Repository and running Docker deployment were inspected read-only. Evidence labels used here are **A** code, **B** runtime, **C** existing artifact, **D** inference, and **E** proposed.

Component 1 currently provides a Sri Lanka tourism knowledge base, BGE semantic retrieval, four evidence adapters (weather, time of day, holiday/event, and historical seasonality), an experimental evidence-aware reranker, and a checkpointed LangGraph research workflow. The production route is not switched to the experimental reranker. Group emotional intelligence is deliberately deferred and contributes no score.

Verified runtime snapshot (B): FastAPI health reported DB/Redis/Qdrant `ok`; PostgreSQL contained 6,120 active attractions, 25 districts, 18 categories, 50 activities, 1,162 weather readings, 129 forecasts, 45 holidays, one tourism event and 165,828 daily climate observations. The active Qdrant replacement collection `sri_lanka_attractions_staging` was green with 6,120 points, 1,024-dimensional cosine vectors. The legacy host-exposed Qdrant collection was unhealthy and is not the store used by the active API container.

The ranking equation is

`final = alpha * normalized_semantic + (1-alpha) * context`, with `alpha=0.65` by request default. R0 is semantic-only; R1 averages available evidence; R2 confidence-weights it; R3 first combines weather and seasonality to avoid double-counting climate. Missing evidence is excluded, not converted to zero. A confirmed closed attraction is forced to zero in R1-R3. Evidence: `app/recommendation/unified_context/reranker.py:26-124` (A).

LangGraph is implemented as parse → validate → clarify/resolve → recommend → verify → compose, with process-local checkpoints and owner isolation. LangChain `StructuredTool` wrappers are used for destination, activity and recommendation calls. Optional LLM intent extraction uses a Groq-compatible `ChatOpenAI`; deterministic parsing remains the default. Evidence: `app/agents/recommendation_graph/builder.py:8-27`, `services/graph_service.py:24-62`, `services/checkpoint_service.py:24-61` (A).

The research APIs are false by default because they are opt-in safety controls, require tokens, and have not completed prospective human validation. False means disabled at runtime, not missing code. See `app/config.py:24-49` and [feature flags](17_FEATURE_FLAGS_AND_CONFIGURATIONS.md).

Latest verified regression evidence from the immediately preceding Stage 12.6 implementation was 116 relevant tests passed (108 unified/context tests plus 8 graph tests), with a real-data graph pilot of 3 requests, 15 candidates and zero graph errors (B/C). This is software reliability evidence, not recommendation accuracy. Stage 12.4G human validation remains pending.

Key defensible claim: the system implements an explainable, Sri Lanka-specific, hybrid structured/vector recommendation research platform with context-aware experimental reranking. Claims not yet defensible: production effectiveness, independently validated accuracy, group-emotion integration, NCF, GNN recommendation, LSTM weather forecasting, or a genetic optimizer.

