# Stage 12.6 Repository Audit

## Existing implementation

Stage 12.5 already provides semantic retrieval through Qdrant, PostgreSQL attraction hydration, four isolated context adapters, deterministic R0-R3 reranking, structured evidence/explanations, and a separately protected research route. `app/agents/graph.py` existed but contained no orchestration implementation. LangChain was already pinned; LangGraph was not installed.

Reusable interfaces were `SemanticAttractionRetriever`, `UnifiedContextOrchestrator`, `UnifiedContextRequest`, `UnifiedContextResponse`, and the weather, time-of-day, holiday/event, and seasonality adapters. Async SQLAlchemy sessions are request scoped. The graph therefore calls the orchestrator directly instead of using internal HTTP or duplicating retrieval/scoring.

## Required extensions

- Add a district constraint to `UnifiedContextRequest`; its default is `None`, preserving old callers and R0-R3 mathematics.
- Add LangGraph, structured LangChain tools, typed graph state, checkpointed clarification, deterministic entity resolution, verification, and a separate API.
- Keep persistent production checkpointing pending; the implemented `MemorySaver` is explicitly development/research only.

## Preserved areas

The Stage 12.5 adapters/reranker, Qdrant collection and embedding dimensions, production routing, and Stage 12.4G evaluation files were not rewritten. Group emotional intelligence and R4 are deliberately not integrated because Component 3 is incomplete and the project owner deferred them.
