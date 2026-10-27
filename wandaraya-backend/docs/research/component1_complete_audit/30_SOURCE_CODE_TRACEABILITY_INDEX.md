# Source Code Traceability Index

| Capability | Primary evidence |
|---|---|
| configuration/flags | `app/config.py:3-55` |
| API registration/security | `app/main.py`; `app/routers/unified_context_research.py`; `app/routers/langgraph_recommendations.py` |
| ingestion | `app/knowledge_base/pipelines/attraction_ingestion_pipeline.py` |
| Google/Wikimedia | `app/knowledge_base/connectors/google_places.py`; `mediawiki.py` |
| semantic document | `app/knowledge_base/embeddings/document_builder.py` |
| embedding | `embedding_service.py:18-90` |
| Qdrant upsert | `qdrant_indexer.py:39-78` |
| semantic search | `app/knowledge_base/retrieval/semantic_retriever.py:41-156` |
| weather source/model | `app/weather_model/context/source_selector.py`; `forecasting/prophet_trainer.py` |
| time context | `app/time_context/evaluator.py`; `service.py` |
| holiday/event | `app/holiday_event/context_features.py`; `context_scoring.py`; `config/holiday_event_scoring.yaml` |
| seasonality | `app/climate/services/seasonality_features.py`; read service/mappings |
| unified engine | `app/recommendation/unified_context/orchestrator.py`; `reranker.py`; schemas/adapters |
| graph | `app/agents/recommendation_graph/builder.py`; nodes/routing/state |
| LangChain tools/LLM | `app/agents/recommendation_graph/tools`; `services/llm_service.py`; `graph_service.py` |
| checkpointing | `services/checkpoint_service.py:24-61` |
| deployment | `docker-compose.yml`; `requirements.txt` |
| scheduled jobs | `airflow/dags` |
| tests | `tests`; `tests/agents` |
| evaluation | `data/reports/stage12_4*`, `stage12_5*`, `stage12_6*` |

Evidence precedence is current code (A), executed runtime (B), current artifacts (C), inference (D), proposal (E). An older `wandaraya_component1_implementation_audit.json` says unified/LangGraph were absent; it is stale relative to current code/runtime and must not override A/B evidence.

