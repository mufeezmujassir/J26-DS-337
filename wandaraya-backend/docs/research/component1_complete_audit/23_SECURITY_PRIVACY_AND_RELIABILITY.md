# Security, Privacy and Reliability

Verified safeguards: environment-based secrets; research/internal token checks; constant-time comparison on unified/internal routes; minimum 32-character configured tokens; graph owner requirement and SHA-256 owner identifier; session ownership rejection; TTL cleanup; Pydantic validation; SQLAlchemy parameterized queries; adapter and graph timeouts; Wikimedia pacing/retries; explicit feature gates; evidence/provenance; production-routing guards.

Gaps/risks:

- CORS allows `*` while credentials are enabled (`app/main.py`), unsuitable without deployment-level restriction.
- No verified application rate limiter for public endpoints.
- LangGraph checkpoints are process-local, non-durable and unsuitable for multi-replica production.
- Research token is shared-secret style; no user/role authorization was verified.
- External LLM privacy/retention policy is not encoded; keep optional path off until governed.
- No verified prompt-injection evaluation; structured tools and validation reduce but do not eliminate risk.
- No automated cross-store transaction between PostgreSQL and Qdrant.
- Backup/restore and disaster recovery were not demonstrated.
- Dependency versions include broad/duplicate constraints; vulnerability status was not scanned.
- Secrets could leak through operational logging if operators print environments; no real secret was exposed in this audit.

Reliability behavior: adapter exceptions become explicit unavailable evidence, graph execution returns 504 after its bound, closed status is auditable, and missing evidence abstains. Recommended next steps are reverse-proxy rate limiting, scoped auth, durable encrypted checkpoint storage, CORS allow-list, security scanning, backup drills, trace redaction and chaos/failure tests.

