# Complete Parameter Reference

| Parameter | Current/default | Location | Influence |
|---|---:|---|---|
| embedding model | `BAAI/bge-large-en-v1.5` | `app/config.py:14` | changing requires re-embedding |
| embedding dimension | 1024 | `embedding_service.py` | must equal Qdrant vector size |
| vector distance | cosine | `qdrant_indexer.py` | similarity geometry |
| unified max candidates | 50 | `app/config.py:34` | recall versus context latency |
| adapter timeout | 15 s | `app/config.py:35` | lower fails faster; higher delays response |
| semantic alpha | 0.65 | unified request schema | semantic/context trade-off |
| time scores | 1.0/0.5/0.0/null | `time_context/service.py` | open/partial/closed/unknown |
| holiday weights | .20/.35/.25/.20 | scoring YAML | generic/Poya/event/interests |
| climate baseline weights | .45/.25/.15/.15 | `seasonality_features.py:95` | rain/temp/humidity/solar |
| comfort temperature | 25°C, sigma 5 | `seasonality_features.py:77-79` | climate comfort curve |
| humidity threshold/span | 65% / 30% | `seasonality_features.py:81-82` | humidity penalty |
| live horizon | 5 days | `source_selector.py:11` | live API eligibility |
| monthly horizon | 90 days | `source_selector.py:12` | approved model eligibility |
| Prophet changepoint prior | .05 | `prophet_trainer.py` | trend flexibility |
| Prophet seasonality prior | 10 | same | seasonality flexibility |
| Prophet interval width | .80 | same | uncertainty interval |
| minimum training months | 24 | same | training eligibility |
| graph clarifications | 3 | `app/config.py:46` | loop bound |
| graph timeout | 45 s | `app/config.py:47` | total execution bound |
| session TTL | 3600 s | `app/config.py:48` | in-memory session lifetime |
| intent model | llama-3.3-70b-versatile | `app/config.py:49` | optional parsing model |
| LLM temperature | 0 | `graph_service.py:28-29` | deterministic tendency |

All research weights are heuristics unless an artifact explicitly reports validation. Increasing alpha protects semantic relevance; decreasing it amplifies available context. Missing features are renormalized, so “missing” is not a zero penalty. Secrets/tokens are intentionally omitted.

