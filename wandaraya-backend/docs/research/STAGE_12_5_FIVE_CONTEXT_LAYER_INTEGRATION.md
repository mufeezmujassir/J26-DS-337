# Stage 12.5 Context-Layer Integration

Despite the original five-layer research proposal, this implementation contains four layers by project-owner direction:

| Layer | Existing implementation reused | Stage 12.5 status |
|---|---|---|
| Weather | `WeatherContextService`, `WeatherSuitabilityEngine` | Integrated |
| Time of day | Stage 12.2 schedule parser/evaluator | Integrated |
| Holiday/Poya/event | Stage 12.3 scoring service | Integrated |
| Historical seasonality | Stage 12.4F conservative scoring service | Integrated |
| Group emotion | None | Deferred; not integrated |

The engine continues with partial evidence. An adapter error is represented as `ERROR`; unsupported or absent evidence has a null score.
