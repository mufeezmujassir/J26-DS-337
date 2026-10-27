# Complete System Architecture

## Implemented architecture

```mermaid
flowchart LR
  S[Google Places / Wikimedia / OpenWeather / NASA POWER / calendars/events] --> I[Validation, normalization, deduplication, mapping]
  I --> PG[(PostgreSQL + PostGIS)]
  PG --> D[Semantic document builder]
  D --> B[BGE-large-en-v1.5, 1024-D normalized vector]
  B --> Q[(Qdrant cosine collection)]
  U[User request] --> G[LangGraph research workflow]
  G --> R[Semantic retriever]
  R --> Q
  R --> PG
  PG --> C[Weather / time / holiday-event / seasonality adapters]
  C --> X[R0-R3 experimental reranker]
  X --> V[Verification and evidence explanations]
  V --> API[FastAPI response]
  GE[Group emotion] -. deferred; no score .-> X
```

Evidence: `app/main.py`, `app/knowledge_base/pipelines/attraction_ingestion_pipeline.py`, `app/recommendation/unified_context/orchestrator.py:47-128`, and `app/agents/recommendation_graph/builder.py:8-27` (A).

## Request sequence

```mermaid
sequenceDiagram
  participant Client
  participant API as FastAPI research route
  participant Graph as LangGraph
  participant Sem as BGE/Qdrant retriever
  participant DB as PostgreSQL
  participant Ctx as Four adapters
  Client->>API: message, session, R0-R3, owner/token
  API->>Graph: execute with 45 s timeout
  Graph->>Graph: parse and validate
  alt missing required intent
    Graph-->>Client: clarification required
  else complete intent
    Graph->>Sem: semantic request
    Sem->>DB: hydrate active attractions
    Graph->>Ctx: evidence batches
    Ctx->>DB: contextual records
    Graph->>Graph: rerank, verify, compose
    Graph-->>Client: traceable recommendation response
  end
```

## Data and deployment

```mermaid
flowchart TB
  subgraph Docker
    F[FastAPI cutover]
    P[(PostGIS 17)]
    RD[(Redis 8)]
    QR[(Qdrant replacement 1.19.1)]
    A[Airflow 3.0.4]
    M[MinIO]
  end
  A --> F
  F --> P
  F --> RD
  F --> QR
  A --> P
  A --> M
```

The active FastAPI environment points to `http://qdrant-production-replacement:6333` and uses `sri_lanka_attractions_staging` (B). `docker-compose.yml` defines both legacy and replacement Qdrant services; service existence does not prove successful scheduled executions.

## Database interaction and evaluation

```mermaid
flowchart LR
  Tests[pytest suites] --> Units[unit/mocked behavior]
  Pilot[shadow pilots] --> Live[real DB/Qdrant execution]
  Protocol[12.4G frozen protocol] --> Humans[prospective human judgments: pending]
  Units --> Report[research artifacts]
  Live --> Report
  Humans -. not collected .-> Report
```

Production routing remains separated by false feature flags. The frontend repository was not present, so UI integration is `NOT_VERIFIED`.

