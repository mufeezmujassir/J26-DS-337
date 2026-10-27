# Viva Question Bank (80 Questions and Answers)

Answers distinguish verified implementation from inference. Likely follow-ups are included after `Follow-up:`.

## Research problem and architecture

1. **What problem does Component 1 solve?** It closes the gap between semantic attraction relevance and real travel suitability using dated local evidence. See `app/recommendation/unified_context`. Follow-up: accuracy is not yet prospectively validated.
2. **Why are conventional recommenders insufficient?** A textually relevant place can be closed or weather/seasonally unsuitable. This is the research motivation, not a claim that every conventional system lacks context.
3. **Who is the target user?** A traveler requesting Sri Lankan attractions with destination, activity and temporal constraints; demographic validation remains future work.
4. **What are the inputs?** Query/message, travel datetime, duration, destination/activity/interests, limits and R0-R3 configuration. See unified and graph request schemas.
5. **What are the outputs?** Candidates with original/final scores and ranks, evidence, contributions, provenance, confidence, limitations and explanation.
6. **What is the end-to-end flow?** Sources → PostgreSQL/PostGIS → semantic document/BGE → Qdrant → active hydration → four adapters → R0-R3 → graph verification → API.
7. **What is the system’s strongest design property?** Missing evidence is explicit and traceable rather than fabricated; this is visible in schemas/reranker.
8. **Is it production enabled?** No. Research flags default false and production-ranking flags remain false (`app/config.py:24-49`).

## Knowledge base and sources

9. **Why use a hybrid knowledge base?** Relational data gives integrity/provenance/geography; Qdrant gives efficient dense similarity. Each store solves a different query.
10. **Why PostgreSQL?** It provides transactions, constraints and relational joins. PostGIS adds spatial types/operations. Selection rationale is technically inferred unless documented.
11. **Why Qdrant instead of only PostgreSQL/pgvector?** The code already uses a dedicated vector engine with cosine/payload search; pgvector could reduce synchronization cost but was not benchmarked.
12. **What is the canonical identity?** The PostgreSQL attraction ID. Qdrant stores it in payload and results are rehydrated from active rows.
13. **How are duplicates handled?** The ingestion pipeline performs identity/deduplication before upsert; semantic retrieval also de-duplicates returned IDs.
14. **What fields form the semantic document?** Name, location, categories, activities, Wikipedia description and Wikivoyage travel context (`document_builder.py`).
15. **What Google data is used?** Identity, address/location, types, ratings/count, website/phone, hours, price/business status, map URI and photo metadata (`google_places.py`).
16. **How are Wikimedia requests polite?** Per-host pacing, a user agent, bounded retries and Retry-After handling (`mediawiki.py`).
17. **Is TripAdvisor integrated?** No connector was found; mark it not implemented rather than planned-as-built.
18. **Is SLTDA live data integrated?** Artifacts/governance code exist, but a current direct production feed was not proven.
19. **How many attractions exist?** The audit observed 6,120 active PostgreSQL rows and 6,120 points in the active replacement collection.
20. **What happens if PostgreSQL and Qdrant disagree?** Hydration drops stale/inactive vector IDs, but missing vectors reduce recall; there is no verified atomic cross-store transaction.

## Embeddings and retrieval

21. **Which embedding model is used?** `BAAI/bge-large-en-v1.5`, configured in `app/config.py:14` and enforced as 1,024-D.
22. **Why BGE rather than MiniLM?** BGE is implemented; no local head-to-head proves superiority. MiniLM is smaller/faster and should be benchmarked before claims.
23. **Why not E5?** It is a valid retrieval alternative, but no repository comparison exists; correct E5 prompting and full re-indexing would be needed.
24. **Are vectors normalized?** Yes, `normalize_embeddings=True`; that stabilizes cosine/dot-product geometry.
25. **What is cosine similarity?** `(q·d)/(||q||||d||)`; higher means closer direction, not causal user preference.
26. **Was BGE fine-tuned?** No fine-tuning evidence was found; it is used as a pretrained sentence encoder.
27. **What happens if dimension changes?** Qdrant rejects mismatched vectors; create a new collection and re-embed all active documents.
28. **How is original order preserved?** Qdrant IDs/scores are stored in order, PostgreSQL rows are mapped by ID, then candidates are rebuilt in vector order (`semantic_retriever.py`).
29. **How are stale attractions filtered?** PostgreSQL hydration requires `Attraction.is_active=True`.
30. **What is top-K’s trade-off?** Higher K may improve recall but increases hydration and four-layer scoring latency; it does not guarantee precision.

## Weather

31. **Which weather approaches are actually used?** OpenWeather short-term API, historical observations, approved monthly-model contract, climatology, Prophet candidate model and rule-based suitability.
32. **Is an LSTM used?** No Component 1 LSTM implementation was verified.
33. **When is live weather selected?** For 0-5 days ahead (`source_selector.py`).
34. **What happens from 6-90 days?** The service requires a production-approved monthly model run; absent approval, evidence can be unavailable.
35. **What happens beyond 90 days?** Historical monthly climatology is returned and clearly labelled, not a day-specific forecast.
36. **What Prophet parameters are used?** Linear/additive yearly model, priors .05/10, 80% interval, minimum 24 months (`prophet_trainer.py`).
37. **Why clip negative rain?** Monthly rainfall is physically nonnegative; clipping is a constraint, not a complete probabilistic rainfall model.
38. **How does weather affect activity?** Rules compare evidence with activity profiles and apply bounded temperature/rain penalties; heuristics need calibration.

## Time of day

39. **What are the time scores?** Enough open time 1.0, insufficient remaining time .5, confirmed closed 0, unknown null (`time_context/service.py`).
40. **Why not score unknown as zero?** Zero means negative evidence; unknown means no evidence and is excluded to avoid unfair penalty.
41. **What timezone is used?** `Asia/Colombo`, preventing server-time ambiguity.
42. **How are overnight hours handled?** The evaluator recognizes intervals crossing midnight (`time_context/evaluator.py`).
43. **What if arrival is near closing?** If remaining time is below visit duration, the score is .5.
44. **Can Poya automatically mark a place closed?** No. Poya relevance does not prove opening status without explicit hours/closure evidence.

## Holiday, event and seasonality

45. **What holiday weights are used?** .20 holiday, .35 Poya, .25 verified event, .20 interests (`config/holiday_event_scoring.yaml`).
46. **How were those weights chosen?** They are documented heuristic research weights, not statistically optimized.
47. **Are all events scored?** No, only verified events are eligible; candidate/unverified events remain evidence but do not get the verified score.
48. **Does every holiday boost every attraction?** No. Eligibility, relevance and missing-feature rules prevent that assumption.
49. **Why is Poya modeled separately?** It is Sri Lanka-specific cultural evidence, but the scorer prevents generic-holiday double counting.
50. **What is the seasonality model?** Explainable district/month climate features and attraction/activity mappings; statistical/rule-based, not neural.
51. **What variables enter Baseline B?** Rainfall favorability .45, temperature comfort .25, humidity comfort .15, solar .15.
52. **Why does seasonality return unavailable?** No trustworthy attraction/activity mapping or profile exists; abstention is intentional.
53. **What does 0.5° NASA POWER resolution imply?** District/grid climatology may miss attraction microclimates; provenance must state that limitation.
54. **What Stage 12.4 result exists?** Exploratory NDCG@5 around .897/.916, but prospective human validation remains pending.

## Unified reranking

55. **What is the formula?** `F=alpha*S+(1-alpha)*C`, default alpha .65; R0 uses only S (`reranker.py`).
56. **Why alpha .65?** It is a conservative heuristic favoring the semantic baseline, not an empirically optimal value.
57. **What differs between R0-R3?** R0 semantic; R1 equal available evidence; R2 confidence-weighted; R3 combines weather/seasonality first.
58. **Why combine weather and seasonality?** Both express climate-related suitability; R3 prevents them from receiving two independent votes.
59. **How are missing dimensions treated?** Excluded from denominator; if none are available, final remains semantic.
60. **What happens when an attraction is closed?** In R1-R3 a verified closed state forces final score to zero while retaining the item for auditability.
61. **How is semantic score normalized?** `clip((score+1)/2,0,1)` in `orchestrator.py:27-28`.
62. **How do you explain rank changes?** The response carries original/final ranks, movement and normalized weighted contributions.

## LangGraph and LangChain

63. **Why LangGraph instead of direct Python?** Multi-turn clarification, conditional routing, checkpointing and traceable nodes justify it; direct Python remains simpler for single-shot work.
64. **Is LangGraph the same as graph recommendation?** No. LangGraph orchestrates control flow; a graph recommender ranks from entity/interaction graph structure.
65. **Which graph nodes exist?** Parse, validate, clarify, resolve destination, resolve activity, recommend, verify and compose (`builder.py`).
66. **How is multi-turn state maintained?** `MemorySaver` plus internal thread UUID, owner hash, session record and TTL.
67. **Is checkpointing production ready?** No; it is process-local, non-durable and explicitly development-only.
68. **How is session isolation enforced?** A public session is claimed by a SHA-256 owner hash; a different owner receives 403.
69. **What does LangChain do?** It supplies structured tools and optional `ChatOpenAI` intent extraction; LangGraph owns workflow state/routing.
70. **Which LLM is configured?** Optional `llama-3.3-70b-versatile` via Groq-compatible endpoint, temperature zero; disabled by default.
71. **How are hallucinations limited?** Deterministic fallback, typed intent, database-backed tools, result verification and provenance; risk is reduced, not eliminated.
72. **What is the graph timeout?** 45 seconds; API maps timeout to HTTP 504.

## Group emotion, evaluation, security and limits

73. **Is group emotion integrated?** No. It is explicitly deferred, flags are false, and it contributes no R0-R3 score.
74. **What is Component 1 versus Component 3?** Component 1 retrieves/contextualizes/orchestrates tourism recommendations; group decision/emotion artifacts are separate and incomplete for this integration.
75. **How do you know recommendations are accurate?** We do not yet have prospective human evidence; tests and pilots establish operation, not relevance accuracy.
76. **How will accuracy be validated?** Frozen queries/items, independent judgments, reviewer agreement, R0-R3 ablation, NDCG/precision/recall and confidence intervals.
77. **What security protects research APIs?** Independent flags, strong configured tokens, owner isolation, timeouts and production guards; scoped auth/rate limiting remain gaps.
78. **What happens if Qdrant fails?** Semantic retrieval fails/returns controlled error; no verified automatic relational semantic fallback exists.
79. **What part is novel?** The domain-specific combination of traceable Sri Lankan contextual evidence, abstention, climate redundancy control and agent workflow; components individually are standard.
80. **What are the highest-priority next steps?** Complete Stage 12.4G human validation, calibrate via non-leaky ablation, harden security/state/backups, then consider guarded production and later group-emotion R4.

