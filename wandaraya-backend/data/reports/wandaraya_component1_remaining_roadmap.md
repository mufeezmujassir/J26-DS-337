# WANDARAYA Component 1 — remaining implementation roadmap

## Audit boundary

This roadmap is based on the static implementation audit dated 2026-10-18. It distinguishes executable source and saved reports from plans. It does not authorize data writes, paid API calls, retraining, Qdrant recovery, or production cutover.

## Priority 0 — restore a safe semantic-index foundation

**Why first:** Semantic retrieval and every retrieval-driven recommendation capability depend on a healthy vector store.

1. Free sufficient host disk capacity without deleting `qdrant-data` or the saved snapshot.
2. Build an isolated staging Qdrant collection in a named Docker volume using a supported version, rather than reusing the production Windows bind mount.
3. Implement a resumable full PostgreSQL-to-staging indexing CLI using `BAAI/bge-large-en-v1.5`, 1,024-dimensional vectors, stable attraction-ID point IDs, document hashes, and checkpoints.
4. Validate staging with complete pagination, filtered scroll, direct point retrieval, vector search, payload IDs, vector dimensions, hashes, and count diagnostics.
5. Prepare—not execute—a separately reviewed production cutover plan only after staging passes.

**Current evidence:** `data/reports/stage_10_1_3e_gate5e2d4b_all_completed_v1_summary.json` is `NOT_READY_FOR_QDRANT_EXECUTION`; the 24 IDs `6604`–`6627` remain outside production Qdrant.

## Priority 1 — complete the recommendation baseline before research models

**Why next:** There is no final recommendation ranker yet. Adding NCF, graph learning, or agents before a deterministic baseline would make research evaluation unclear.

1. Create a content-based baseline ranker using semantic relevance plus transparent attraction metadata signals.
2. Define a stable recommendation request/response contract and register an actual `/api/v1/recommendations/...` ranking endpoint.
3. Keep semantic retrieval as candidate generation; make ranking, tie-breaking, diversity, provenance, and unavailable-context behavior explicit.
4. Add offline retrieval and ranking evaluation datasets, metrics, and deterministic regression tests.

**Do not call the current context-enrichment endpoint a recommendation engine:** `app/recommendation/context_enrichment/service.py` explicitly does not rerank and emits `ranking_applied=false`.

## Priority 2 — finish the five independent context dimensions

**Dependency:** Requires the baseline ranker contract, but each dimension can be implemented and tested independently.

1. **Time of Day:** persist verified opening-hours evidence, evaluate applicability for a planned visit time, and expose a typed score/unknown result. Existing parser/evaluator: `app/time_context/opening_hours/`.
2. **Poya/Holiday:** populate and validate a Sri Lankan calendar source; create crowd/access rules with provenance. The current `HolidayCalendar` model alone is not a scoring layer.
3. **Seasonality:** convert verified seasonal guidance and `best_visit_months` into an explainable, source-aware score. Do not infer unsupported seasons.
4. **Group Emotion:** define research consent, data model, signal acquisition, privacy policy, and a testable emotion-to-preference adapter. No implementation currently exists.
5. **Weather:** retain the independent adapter already in `app/recommendation/context_dimensions/weather_adapter.py`; keep unknown weather as unknown rather than fabricating a score.

## Priority 3 — build the unified Context Re-Ranker

1. Define a canonical candidate envelope shared by all five context dimensions.
2. Define weights/configuration, missing-data policy, confidence propagation, explanations, and reproducible versioning.
3. Ensure context dimensions do not overwrite semantic evidence.
4. Add controlled fixtures covering conflicts, unavailable context, and deterministic ties.
5. Evaluate the re-ranker against the content-based baseline before claiming improvement.

The current `app/context_stack/__init__.py` is empty; only a weather adapter is present. A five-layer system is therefore not yet implemented.

## Priority 4 — weather operational maturity

1. Review registry candidates using the existing evidence and manually approve only supported models.
2. Trigger Airflow DAGs deliberately in a non-production validation environment and capture real task-instance results. The existing weather validation report confirms DAG import, not real task execution.
3. Verify live-provider cache behavior, credentials, rate limits, and five-day horizon in deployed conditions.
4. Preserve the scientific safeguards: 95% minimum temperature coverage, no invented rainfall, no cross-district substitution, and no automatic production approval.

## Priority 5 — research extensions after a baseline exists

### Neural Collaborative Filtering

Needs a consented user–attraction interaction dataset, train/validation/test split strategy, cold-start policy, model training/inference service, baselines, fairness/privacy review, and offline metrics. Nothing in the current repository implements this.

### Graph recommender

Reuse only the appropriate knowledge graph or user-item graph. The existing routing graph is not a recommendation graph. Define nodes/edges, graph-learning approach, candidate generation/ranking integration, and evaluation.

### Genetic itinerary optimization

First establish a scored recommendation set and route/travel-time constraints. Then define chromosomes, objectives, feasibility constraints, repair operators, reproducibility seed, comparison baselines, and evaluation. Current scheduling/routing code is not a genetic algorithm.

### LangGraph orchestration

Only consider after the deterministic APIs and re-ranker are stable. `app/agents/graph.py` is empty and no LangGraph dependency is installed. An agent layer should orchestrate validated tools, not replace ranking logic.

## Delivery sequence

1. Safe Qdrant staging rebuild and validation.
2. Semantic retrieval health verification and incremental index catch-up.
3. Deterministic content-based recommendation baseline and API.
4. Time, Poya/holiday, seasonality, and group-emotion context implementations.
5. Unified five-layer Context Re-Ranker with evaluation.
6. Weather approval/operational validation in a controlled environment.
7. NCF, graph recommender, itinerary optimizer, and LangGraph only when their datasets and research evaluation plans exist.

## Current readiness statement

The project is **conditionally ready** for knowledge-base browsing, weather suitability where reliable data exists, controlled source governance, and research development. It is **not ready** to claim a healthy end-to-end semantic recommendation platform, production long-range model forecasting, a unified five-layer Context Re-Ranker, NCF, graph recommendation, GA itinerary optimization, or LangGraph orchestration.
