# Implementation Status and Roadmap

| Module | Stage | Implemented behavior | Tests/evaluation | Status | Remaining work |
|---|---|---|---|---|---|
| knowledge base | core | structured attractions/taxonomies/provenance | live counts | IMPLEMENTED_AND_TESTED | quality monitoring |
| ingestion | core | Google/Wikimedia pipeline, schedulers | code/tests | IMPLEMENTED_AND_TESTED | observed DAG history/licensing audit |
| BGE/Qdrant | core | 1024-D normalized cosine retrieval | green active collection | IMPLEMENTED_AND_TESTED | backup/sync drill |
| semantic retrieval | 12.1 | query→Qdrant→active hydration | tests/API | IMPLEMENTED_AND_TESTED | relevance benchmark |
| weather | 12.x | source routing + rules; Prophet candidate | artifacts/tests | PARTIALLY_IMPLEMENTED | approved medium model, validation |
| time | 12.2 | opening/remaining-time scoring | tests | IMPLEMENTED_EXPERIMENTAL | calibration/data quality |
| holiday/event | 12.3 | verified evidence scoring | tests; sparse data | IMPLEMENTED_EXPERIMENTAL | event coverage/human validation |
| seasonality | 12.4 | NASA climatology/mappings/profiles | exploratory NDCG | VALIDATION_PENDING | prospective judgments |
| unified reranker | 12.5 | R0-R3, provenance, abstention | shadow/tests | IMPLEMENTED_EXPERIMENTAL | ablation/human validation |
| LangGraph/LangChain | 12.6 | graph, tools, clarification, memory | 8 graph tests/pilot | IMPLEMENTED_EXPERIMENTAL | durable state/load/security |
| group emotion | future | contract/flags only in Component 1 | none integrated | CONTRACT_READY | finish Component 3 and validate |
| NCF/GNN/GA | proposed | none | none | NOT_IMPLEMENTED | justify data and experiments first |
| routing | separate | Dijkstra/ORS APIs | API present | PARTIALLY_IMPLEMENTED | integration boundary |
| replanning/transport | separate | repository modules | wiring unverified | UNKNOWN_REQUIRES_VERIFICATION | end-to-end trace |
| Flutter/UI | external | backend only | unavailable | NOT_IMPLEMENTED/UNKNOWN | verify frontend repo |
| production ranking | safety gate | unchanged semantic production behavior | guard tests | NOT_IMPLEMENTED | validation and approval |

Roadmap: (1) finish data-quality and event coverage; (2) collect Stage 12.4G judgments; (3) run R0-R3 ablation with confidence intervals; (4) calibrate weights without leakage; (5) security/load/failure testing and durable checkpoints; (6) only then consider a guarded production experiment; (7) integrate group emotion later through R4 after its own consent and validation requirements.

