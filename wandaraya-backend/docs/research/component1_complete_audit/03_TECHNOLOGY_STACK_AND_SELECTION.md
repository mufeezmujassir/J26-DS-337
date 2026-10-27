# Technology Stack and Selection

| Technology | Verified role | Location | Status / rationale |
|---|---|---|---|
| Python | Application, pipelines, ML and tests | repository-wide | Implemented |
| FastAPI/Pydantic | Typed HTTP APIs and schemas | `app/main.py`, routers, schemas | Implemented; async/OpenAPI fit is an inferred rationale |
| SQLAlchemy/psycopg | Async relational access | `app/database.py`, repositories | Implemented |
| PostgreSQL/PostGIS | Canonical entities, provenance and geography | models/migrations, Compose | Implemented; relational integrity + spatial types |
| Qdrant | Dense-vector retrieval | `app/knowledge_base/embeddings`, retrieval | Implemented |
| Sentence Transformers/BGE | 1,024-D semantic embeddings | `embedding_service.py` | Implemented; no fine-tuning evidence |
| LangGraph | Stateful conditional orchestration | `app/agents/recommendation_graph` | Implemented, experimental |
| LangChain | `StructuredTool` and optional `ChatOpenAI` | graph tools/services | Implemented, optional LLM path |
| Groq-compatible endpoint | Optional intent model (`llama-3.3-70b-versatile`) | `graph_service.py:24-29` | Disabled by default |
| Prophet | Monthly weather candidate model | `app/weather_model/forecasting` | Implemented/trained pipeline; no production-approved run at audit evidence |
| Pandas/NumPy/scikit-learn | ETL, analysis and metrics | weather/climate/evaluation code | Implemented |
| Redis | cache/infrastructure dependency | config/Compose | Running; not the LangGraph checkpoint store |
| Airflow | Scheduled ingestion/model jobs | `airflow/dags` | Configured; successful schedules not independently verified |
| Docker Compose | Reproducible local services | `docker-compose.yml` | Running on audited host |
| OpenWeatherMap | live 5-day/3-hour weather | weather live client | Implemented, key required |
| NASA POWER | historical climate | climate acquisition/ingestion | Implemented |
| OpenRouteService | route API integration | route config/services | Implemented separately |
| PyTorch/Transformers | embedding/runtime dependencies; other components | requirements | Installed dependency is not proof of a Component 1 neural recommender |

Alternatives such as pgvector, MiniLM, E5, direct Python orchestration and LSTM are technically possible, but no repository decision record proves they were benchmarked and rejected. Any selection explanation beyond code behavior is therefore **D — technical rationale inferred, not documented**. Exact pinned dependencies are in `requirements.txt:1-142` (A).

