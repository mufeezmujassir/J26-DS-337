# PP1 Presentation Preparation

## Core story

Problem: static tourism recommenders may return semantically relevant places that are closed, weather-inappropriate, culturally mismatched or seasonally unsuitable. Objective: produce explainable Sri Lanka-specific recommendations by combining semantic relevance with trustworthy contextual evidence.

Sub-objectives: build a provenance-aware hybrid KB; retrieve natural-language candidates; model four context dimensions; rerank with missing-evidence safety; orchestrate multi-turn requests; establish a prospective evaluation protocol.

Progress claim: semantic KB/retrieval, four adapters, R0-R3 and LangGraph are implemented experimentally; 116 relevant tests passed in the latest verification; a 3-request graph pilot completed without graph errors. Group emotion and prospective accuracy validation remain pending.

## Two-minute script

“Component 1 addresses the gap between textual relevance and practical travel suitability. We built a 6,120-attraction PostgreSQL/PostGIS and Qdrant knowledge base. BGE embeddings retrieve candidates from natural language. Four evidence services then assess weather, time of day, Sri Lankan holiday/Poya/events and historical seasonality. The experimental R0-R3 framework preserves the semantic baseline, excludes missing evidence and prevents weather and seasonality from double voting in R3. LangGraph now manages intent validation, clarification, verified tools and response composition. All research paths remain feature-gated, production order is unchanged, and group emotion is intentionally deferred. Our next research step is independent human evaluation; passed tests show reliability, not recommendation accuracy.”

## Five-minute demo

Minute 1: health and KB counts. Minute 2: semantic query. Minute 3: one context and abstention example. Minute 4: R0 versus R3 trace. Minute 5: LangGraph clarification/resume and evaluation limitation.

Recommended screenshots: architecture diagram, KB status, semantic results, one contribution trace, graph node/tool trace, R0-R3 comparison, and Stage 12.4G “human judgments pending.” Never show tokens or `.env`.

Likely supervisor answer: weights and alpha are heuristic baselines, not optimized claims; the planned evaluation uses frozen queries, independent judgments, ablations, NDCG and agreement statistics.

