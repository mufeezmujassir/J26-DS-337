# Time-of-Day Context

The layer evaluates an attraction’s weekly opening-hours schedule in `Asia/Colombo`, the requested arrival time and visit duration. `app/time_context/evaluator.py` parses normal and overnight intervals; `app/time_context/service.py` produces the score.

Verified rules (A):

| State | Score | Ranking behavior |
|---|---:|---|
| open with enough remaining visit time | 1.0 | positive evidence |
| open but remaining time is shorter than visit duration | 0.5 | partial suitability |
| confirmed closed | 0.0 | unified R1-R3 applies a hard zero restriction |
| unknown/missing hours | null | excluded, never treated as closed or neutral |

These values are heuristic and not empirically calibrated. Larger visit duration makes “insufficient window” more likely. Incorrect hours can cause an incorrect restriction, so explanations retain status/provenance.

Test scenarios should cover normal open, closed, missing schedule, arrival near closing, overnight opening, invalid schedule and timezone conversion. Poya-specific closure is not inferred from generic opening hours; it requires explicit evidence from the holiday/event layer. The read-only LLM advisory module does not alter rank.

Primary evidence: `app/time_context/evaluator.py:37-98`, `app/time_context/service.py:43-105`, and `app/recommendation/unified_context/adapters/time_of_day.py`.

