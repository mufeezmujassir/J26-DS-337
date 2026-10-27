# WANDARAYA Component 1 — Complete Master Report

## Contents

1. Scope and evidence
2. Research problem and objective
3. Architecture and data flow
4. Knowledge base and retrieval
5. Four context layers
6. Unified ranking
7. LangGraph/LangChain orchestration
8. Models, parameters and technologies
9. Execution, tests and evaluation
10. Security, limitations and roadmap

## 1. Scope and evidence

This is a read-only implementation audit dated 2026-10-21. Current code and runtime take precedence over historical reports. A=code, B=runtime, C=artifact, D=inference, E=proposal. No application code, data, flags, models or frozen artifacts were changed; only this audit documentation/JSON was created.

## 2. Problem and objective

The objective is to recommend Sri Lankan attractions that are not merely textually relevant but operationally and seasonally suitable. Inputs include natural-language intent, destination/activity/date/time, duration/interests and configuration. Outputs preserve semantic results and add evidence, experimental score/rank, movement, provenance, confidence, limitations and explanation.

## 3. Architecture

External sources feed validated PostgreSQL/PostGIS entities. The document builder creates attraction text; BGE generates normalized 1,024-D vectors; Qdrant retrieves top-K IDs; PostgreSQL filters/hydrates active rows. Weather, time, holiday/event and seasonality adapters produce optional evidence. R0-R3 rerank experimentally. LangGraph coordinates parse, validate, clarify, resolve, recommend, verify and compose. FastAPI exposes baseline and gated research routes. See [architecture](02_COMPLETE_SYSTEM_ARCHITECTURE.md).

## 4. Knowledge base and semantic retrieval

What/why: structured identity/provenance and vector meaning require complementary stores. Where: `app/knowledge_base`. Data: Google Places plus Wikimedia enrichment and relational taxonomies. Process/output: validated/deduplicated records and Qdrant points. Controls: model, dimension, collection and top-K. Changes: a model/dimension change requires full re-embedding. Run/test: KB status/semantic-search APIs and knowledge tests. Runtime had 6,120 active attractions and matching active vector points.

## 5. Context layers

Weather routes dates across live forecast, approved monthly model, historical observations and climatology; rules evaluate activity suitability. Time parses Colombo schedules and returns 1/.5/0/null. Holiday/event uses verified date/location/interest evidence with heuristic weights. Seasonality maps NASA POWER climatology to attraction/activity evidence and abstains without a mapping/profile. Group emotion is deferred and never scored. Each layer answers what/why/where/input/process/output/parameters/change/run/test in its dedicated chapter 08-14.

## 6. Ranking algorithm

R0 is semantic baseline. R1 equally averages available evidence. R2 uses evidence confidence. R3 combines weather and seasonality before the average. `F=.65S+.35C` by default; missing evidence is excluded and a confirmed closure is a hard zero outside R0. The system preserves both ranks and contribution traces. Parameters are heuristic and production switching is blocked.

## 7. Orchestration

LangGraph is a workflow graph, not a recommender graph. It enables conditional clarification and resumable state. LangChain provides structured tools and an optional Groq-backed intent parser; deterministic behavior is default. Memory is process-local with owner hash, internal thread UUID and TTL. Run through the protected research endpoint with isolated flags/token/owner; test with `tests/agents`.

## 8. Models and technology

Actual models/algorithms: BGE embeddings, cosine retrieval, rule/weighted context scores, Prophet monthly candidate forecasting, statistical climatology, R0-R3 blend and Dijkstra routing separately. NCF, GNN recommender, LSTM weather and GA optimizer are absent. PostgreSQL/PostGIS, Qdrant, FastAPI, SQLAlchemy, Airflow, Docker, Redis, LangGraph/LangChain, Pandas/NumPy and external APIs are verified. Selection superiority is not experimentally proven.

## 9. Execution, tests and evaluation

Start Docker Compose, inspect services, call `/health` and KB status, then run pytest. Latest relevant verification was 116 passing tests and a 3-request/15-candidate graph pilot with zero graph errors. Stage 12.4F exploratory NDCG exists, but Stage 12.4G has no human judgments. Tests and availability are not accuracy. A valid final evaluation needs frozen queries, independent relevance/context labels, R0-R3 ablation, NDCG/precision/recall, agreement and confidence intervals.

## 10. Security, limitations and roadmap

Research routes are token/flag gated with timeouts and production guards. Risks include wildcard CORS, missing rate limiting/scoped auth, in-memory checkpoints, external-provider governance, cross-store consistency and unverified backup drills. Next: prospective validation, calibrated weights, durable secure checkpoints, performance/security testing, then a controlled production experiment. Group emotion comes later through a separately validated R4 contract.

## Reproducible navigation

Use chapters 03-07 for stack/KB/retrieval, 08-14 for context/orchestration, 16-20 for parameters/APIs/execution/demo, 21-26 for verification/research/status, and 27-30 for viva/presentation/troubleshooting/traceability. Machine-readable facts are under `data/reports/component1_complete_audit`.

