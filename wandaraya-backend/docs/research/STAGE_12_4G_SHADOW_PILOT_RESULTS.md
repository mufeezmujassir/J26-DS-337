# Stage 12.4G Shadow Pilot Results

The pilot ran inside `wandaraya-api-cutover` against PostgreSQL/PostGIS and `qdrant-production-replacement`, using BAAI/bge-large-en-v1.5. Three real semantic requests returned 15 candidates. Original and returned orders matched for all requests; a repeated request was deterministic; the error rate was 0; and production reranking remained disabled.

End-to-end latencies were 18,729.50 ms (cold embedding-model path), 1,427.03 ms, and 395.70 ms. Mean/median/max were 6,850.74 / 1,427.03 / 18,729.50 ms. Mean seasonality attachment latency was 72.29 ms (maximum 119.45 ms). SQLAlchemy instrumentation counted 10 database statements per request across retrieval metadata, time, holiday/event, and climate dimensions. Seasonality itself used two batched statements per request. Seasonality evidence was available for 10/15 candidates; district-proxy frequency was 9/15; observed fallback frequency was 0/15 in these semantic cases.

These are environment-specific pilot measurements, not production service-level objectives. Full measurements are in `data/reports/stage12_4g_shadow_pilot.json`.

