# Stage 12.5 Unified Context Architecture

Stage 12.5 is a four-layer, research-only pipeline:

`semantic retrieval → candidate hydration → weather/time/holiday/seasonality evidence → R0–R3 reranker → explanations`

The adapters use one request-scoped SQLAlchemy `AsyncSession`. Database-backed calls are batched and executed sequentially because concurrent operations on one session are unsafe. Every adapter has a timeout and failure isolation. Missing evidence remains null and never removes a candidate. Supplied candidates may replace semantic retrieval when they carry an attraction ID and semantic score.

The implementation is under `app/recommendation/unified_context/`. Group emotional intelligence is explicitly deferred and has no adapter, request field, weight, or scoring path in this version.

The production order is copied from the semantic order and never changed. Only the separately labelled experimental order is reranked.
