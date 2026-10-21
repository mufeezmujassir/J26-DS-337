# Stage 12.5 Shadow Pilot Results

The executable pilot is `scripts/run_stage12_5_shadow_pilot.py`. It accepts a JSON array of unified requests and records real semantic retrieval, evidence coverage, per-layer and end-to-end latency, errors, original order, and experimental order.

A real-data engineering pilot ran on 21 October 2026 against the configured PostgreSQL and Qdrant services. Three queries retrieved 10 semantic candidates each and returned five ranked candidates each. All three completed without adapter errors, and production order remained unchanged. Context availability among the 15 returned candidates was weather 5/15, time-of-day 11/15, holiday/event 10/15, and historical seasonality 0/15. Unavailable seasonality mappings remained null.

Cold-start wall latency was 18,806.275 ms, dominated by embedding initialization; the two subsequent requests averaged 714.116 ms. These are descriptive measurements from three scenarios, not a load benchmark. Full evidence and timings are in `data/reports/stage12_5_shadow_pilot.json`, `stage12_5_context_coverage.json`, and `stage12_5_latency.json`. Stage 12.4G's separate completed pilot and artifacts were not modified.
