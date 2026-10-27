# Stage 12.6 Context Integration Status

Despite the original five-context proposal, this implementation intentionally remains a four-context system because the project owner deferred Component 3 integration.

| Context | Adapter/source | Scored when evidence exists | Status |
|---|---|---:|---|
| Weather | Existing weather adapter and approved forecast sources | Yes | Reused |
| Time of day | Opening-hours policy and requested visit window | Yes | Reused |
| Holiday/event | Verified calendar, Poya and event records | Yes | Reused |
| Historical seasonality | Frozen Stage 12.4 mappings and monthly evidence | Yes | Reused; no available pilot scores |
| Group emotion | Component 3 | No | Deferred; not integrated |

Unavailable evidence remains non-numeric and is excluded by the existing reranker. Historical climate is not represented as live weather. The shadow pilot observed real evidence in three of the four implemented layers; this is coverage, not relevance accuracy.
