# Stage 12.6 Graph State and Routing

`RecommendationGraphState` stores serializable identifiers, parsed intent, trusted Asia/Colombo time, resolved IDs, configuration, tool inputs/outputs, verification, errors, warnings, and audit trails. It never stores a database session or credential. Additive reducers are defined for errors, warnings, nodes, and tool calls.

Required fields are destination, date, and exact or approximate visit time. Missing values route to `interrupt()`. A subsequent request with the same authenticated owner and session resumes using `Command(resume=...)`. The maximum clarification count defaults to three. Destination ambiguity re-enters the same bounded clarification path. Optional unsupported activity terms do not stop retrieval.

The development checkpoint registry binds a SHA-256 owner identifier to each session and enforces a one-hour default TTL. This is process-local memory; PostgreSQL-backed durable LangGraph checkpointing and cleanup migrations remain production work.
