# Stage 12.5 Context Evidence Contract

`ContextEvidence` records the dimension, status, nullable score, evidence-quality coefficient, source and version, evaluation date, travel date, provenance, explanation, limitations, missing-data indicators, and fallback details.

Statuses are `AVAILABLE`, `PARTIALLY_AVAILABLE`, `NOT_AVAILABLE`, `NOT_APPLICABLE`, `STALE`, `ERROR`, and `UNSUPPORTED`. Only available or partially available evidence may contain a score. Confidence is a transparent quality coefficient used by R2, not a probability. Evidence without a defensible quality value is excluded from R2 rather than assigned an invented value.

The contract version is `stage12_5_unified_context_v1`.
