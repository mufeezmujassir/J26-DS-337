# Unified Context Reranking

The engine gathers weather, time, holiday/event and seasonality evidence sequentially because they share one SQLAlchemy `AsyncSession`; each call is timeout/failure isolated (`orchestrator.py:86-107`). Group emotion is absent from `CONTEXT_DIMENSIONS` and does not participate.

| Configuration | Actual behavior |
|---|---|
| R0 | normalized semantic score only |
| R1 | equal average of available context dimensions |
| R2 | average weighted by each evidence confidence |
| R3 | combines weather + seasonality first, then averages with other dimensions |

For R1-R3, `F=alpha*S+(1-alpha)*C`, default `alpha=0.65`. Missing evidence is excluded. If all evidence is missing, `F=S`. A verified `CLOSED` time state sets `F=0`. Ties resolve by original semantic rank then attraction ID. Exact implementation: `app/recommendation/unified_context/reranker.py:29-124` (A).

R3 controls climate redundancy: two related climate sources contribute as one averaged component instead of two independent votes. It does not prove statistical independence or optimal weighting.

Outputs preserve original score/rank, final experimental score/rank, movement, per-layer evidence, contributions, provenance, confidence, limitations and explanation. The endpoint is research-only and needs both engine/rerank flags plus API flag and token. `ENABLE_UNIFIED_CONTEXT_PRODUCTION_RANKING=True` is explicitly rejected at this stage (`orchestrator.py:47-51`).

The default alpha and context weights are research heuristics. They require ablation and human ground truth before accuracy claims. Stage 12.5 shadow evidence showed 3 queries, 15 candidates and zero execution errors, not relevance accuracy.

