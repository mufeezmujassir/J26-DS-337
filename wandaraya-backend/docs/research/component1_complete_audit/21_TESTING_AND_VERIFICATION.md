# Testing and Verification

The repository contains 111 test files. Filename grouping found 35 weather, 32 time-related, 6 climate/seasonality, 5 knowledge/embedding/recommendation, 4 holiday/event, 3 unified-context, 4 LangGraph/agent, and additional API/security/integration tests; groups overlap and are not additive.

Latest executed evidence from the Stage 12.6 implementation immediately before this audit: 108 relevant existing unified/context tests plus 8 graph tests passed, zero failed (116 total). The graph pilot processed three requests and 15 candidates with zero graph errors. Artifacts: `data/reports/stage12_6_langgraph_test_results.json` and `stage12_6_langgraph_shadow_pilot.json` (B/C). Historical “120 passed” is not reused as a current run.

Commands:

```powershell
python -m pytest tests/agents -q
python -m pytest tests/test_unified_context* -q
python -m pytest tests -q
python -m pytest --collect-only -q
```

Unit tests commonly mock external APIs and repositories; integration/pilot tests may need Docker DB/Qdrant. Inspect fixtures before running tests against a persistent database. Test success means implemented invariants pass; it does not measure relevance, user satisfaction, or causal context benefit.

Required future verification: full clean-environment suite, dependency vulnerability scan, failure/timeout tests, load/latency distribution, checkpoint restart behavior, real API contract tests, and Stage 12.4G prospective judgments. See the machine-readable test inventory.

