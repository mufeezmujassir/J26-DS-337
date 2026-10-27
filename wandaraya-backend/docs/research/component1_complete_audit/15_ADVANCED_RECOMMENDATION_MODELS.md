# Advanced Recommendation Models

| Approach | Repository status | Evidence-based interpretation |
|---|---|---|
| semantic/content retrieval | IMPLEMENTED_AND_TESTED | BGE + Qdrant + relational hydration |
| context-aware hybrid reranking | IMPLEMENTED_EXPERIMENTAL | semantic and four evidence layers |
| Neural Collaborative Filtering | NOT_IMPLEMENTED | no trained user-item neural model found |
| graph/GNN recommender | NOT_IMPLEMENTED | LangGraph is orchestration, not recommendation learning |
| genetic algorithm optimizer | NOT_IMPLEMENTED | no GA-based ranking/itinerary optimizer found |
| Dijkstra route solver | IMPLEMENTED separately | `/routes/dijkstra`; not a graph recommender |
| trip scheduling/replanning | PARTIALLY_IMPLEMENTED elsewhere | code exists, but no verified Component 1 production wiring |
| transport integration | PARTIAL/SEPARATE | models/loaders exist; ranking integration not proven |
| LSTM weather model | NOT_IMPLEMENTED for Component 1 | Prophet/rules/API/climatology are verified |

NCF would require sufficient user-item interactions and is weak for new users/items without side information. GNN recommendation would require a meaningful entity/interaction graph and evaluation. A GA is useful for constrained itinerary optimization but is unnecessary for single-list reranking. These are general comparisons, not claims of repository experiments.

The chosen architecture is appropriate to the current data: rich attraction text/metadata and contextual evidence are available, while verified behavioral interaction data is not demonstrated. Future advanced models should be compared against R0-R3 using frozen queries and independent judgments rather than added for terminology value.

