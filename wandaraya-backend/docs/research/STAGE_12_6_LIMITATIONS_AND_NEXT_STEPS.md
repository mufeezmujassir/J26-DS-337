# Stage 12.6 Limitations and Next Steps

- Group emotion and R4 are deliberately deferred until Component 3 is complete and an attraction-specific mapping is validated.
- MemorySaver is suitable for local research only; durable PostgreSQL checkpointing, migrations, retention jobs, and multi-worker concurrency tests remain pending.
- Deterministic response templates are active. Optional LLM extraction exists behind a flag; optional LLM prose generation remains disabled and is not required for correctness.
- The three-query real-data pilot returned 15 candidates without graph errors. Cold-start latency was 39,786.613 ms; warm latencies were 4,737.157 and 745.332 ms. These runs do not validate relevance.
- Seasonality provided 0/15 available scores. That is reported as actual missing coverage and must be investigated without changing frozen evaluation artifacts.
- Independent blinded human relevance and satisfaction evaluation remains pending.

Next: complete Component 3 separately, define privacy/consent and relevance contracts, add durable checkpointing, expand integration/security testing, and conduct the already planned independent evaluation before any production activation.
