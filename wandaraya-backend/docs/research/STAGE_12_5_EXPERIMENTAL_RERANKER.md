# Stage 12.5 Experimental Reranker

All policies are experimental and uncalibrated:

- R0: normalized semantic relevance only.
- R1: equal weight across available context evidence.
- R2: available evidence weighted by the adapters' documented quality coefficients.
- R3: R1 with weather and historical seasonality conservatively averaged into one climate component when both exist.

For R1–R3, `final = alpha × semantic + (1-alpha) × context`, with default `alpha=0.65`. Missing scores are excluded from the denominator. Ties use original semantic rank and then attraction ID. A confirmed closed state remains in the audit response but receives a final score of zero, so positive context cannot bypass a verified closure.

R4 is not implemented because group emotional intelligence is deferred.
