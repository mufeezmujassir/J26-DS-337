# Stage 12.6 Test Results

Executed in the FastAPI container on 2026-10-21:

```text
python -m pytest -q tests/agents/recommendation_graph -x
8 passed in 20.84s

python -m pytest -q tests/recommendation/test_unified_context_schemas.py tests/recommendation/test_unified_context_reranker.py tests/recommendation/test_unified_context_adapters.py -x
108 passed in 23.32s
```

Total executed: 116 passed, 0 failed. Coverage includes deterministic intent/date parsing, injection detection, graph compilation, clarification interrupt/resume, successful completion, verifier failure, unchanged production order, disabled API, dedicated authentication, and session ownership. No paid LLM call occurs in tests.

The live API health check passed and a disabled-by-default endpoint request returned HTTP 503 as designed.
