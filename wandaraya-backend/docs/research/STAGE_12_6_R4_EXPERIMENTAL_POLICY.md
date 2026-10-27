# Stage 12.6 R4 Experimental Policy

R0-R3 remain unchanged:

- R0: semantic baseline.
- R1: available-context equal weighting.
- R2: evidence-quality-aware weighting.
- R3: weather/seasonality redundancy control.

R4 is not implemented. Component 3 is incomplete and there is no validated attraction-specific mapping from group emotion to suitability. `ENABLE_GROUP_EMOTION_CONTEXT`, `ENABLE_R4_EXPERIMENTAL_RERANKING`, and production routing all default to false. Missing emotion is not converted to zero and the system does not claim five-layer execution.
