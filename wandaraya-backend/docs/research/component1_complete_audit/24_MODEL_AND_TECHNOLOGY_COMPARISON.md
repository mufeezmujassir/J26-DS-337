# Model and Technology Comparison

| Family | Strength | Cost/requirement | Component 1 decision/status |
|---|---|---|---|
| content/semantic | handles cold-start items from text | embedding/index compute | implemented |
| NCF | learns behavior patterns | large interaction matrix; cold start | absent |
| graph/GNN recommendation | relation-aware | graph design/training complexity | absent; LangGraph is unrelated orchestration |
| context reranking | interpretable operational relevance | context coverage/calibration | implemented experimentally |
| BGE large | strong general retrieval representation, 1024-D | more RAM/latency than small encoders | implemented; superiority not locally measured |
| MiniLM | compact/fast | lower capacity/dimension | conceptual alternative |
| E5 | retrieval-oriented encoder family | requires correct prompting/evaluation | conceptual alternative |
| direct Python orchestration | simplest and transparent | manual state/branch handling | unified engine uses it |
| LangChain | tool/model abstractions | abstraction/version overhead | structured tools + optional LLM |
| LangGraph | conditional/resumable state | added runtime/checkpoint complexity | experimental graph implemented |
| API forecast | best near-term provider data | external dependency/cost | 0-5 days |
| Prophet | interpretable seasonal trend | monthly/univariate limits | candidate; no approved production run |
| LSTM | flexible nonlinear sequence model | data/compute/tuning, poor interpretability | not implemented |
| climatology | robust long-range expectation | not date-specific | long-range evidence |
| PostgreSQL/PostGIS | integrity and spatial SQL | not specialized dense search | canonical store |
| Qdrant | vector search/payload filtering | second-store synchronization | semantic index |

These are general engineering comparisons (D) unless marked as measured. The repository contains no controlled BGE-versus-MiniLM/E5, Prophet-versus-LSTM, or Qdrant-versus-pgvector experiment; do not claim universal superiority.

