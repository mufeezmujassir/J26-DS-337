# Feature Flags and Configuration

The false defaults are safety controls, not evidence that the code is absent.

| Flag | Default | Meaning |
|---|---|---|
| `ENABLE_UNIFIED_CONTEXT_ENGINE` | false | master Stage 12.5 opt-in |
| `ENABLE_UNIFIED_CONTEXT_EXPERIMENTAL_RERANKING` | false | permits R1-R3 execution |
| `ENABLE_UNIFIED_CONTEXT_RESEARCH_API` | false | exposes protected research route |
| `ENABLE_UNIFIED_CONTEXT_PRODUCTION_RANKING` | false | must remain false; true is rejected |
| `ENABLE_LANGGRAPH_RECOMMENDATION_ENGINE` | false | enables graph runtime |
| `ENABLE_LANGGRAPH_RESEARCH_API` | false | exposes protected graph route |
| `ENABLE_LANGCHAIN_INTENT_EXTRACTION` | false | optional external LLM intent parser |
| `ENABLE_LANGCHAIN_LLM_EXPLANATIONS` | false | optional LLM explanation path |
| `ENABLE_GROUP_EMOTION_CONTEXT` | false | deferred component |
| `ENABLE_R4_EXPERIMENTAL_RERANKING` | false | reserved future configuration |
| `ENABLE_LANGGRAPH_PRODUCTION_ROUTING` | false | production graph switching prohibited |

Why false: experimental behavior must not silently alter users’ ordering; research endpoints need deliberate credentials; LLM calls add cost/data/provider failure; in-memory graph state is not production durable; prospective relevance validation is unfinished; group emotion is incomplete. Evidence: `app/config.py:22-49` and both research routers (A).

For an isolated research demo, set only the required research flags and a strong token in the container environment, keep both production flags false, restart the API container, and call the research endpoint. Never commit secrets or print `.env`. The audit changed no flags.

