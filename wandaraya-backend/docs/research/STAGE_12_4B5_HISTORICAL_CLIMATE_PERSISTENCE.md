# Stage 12.4B.5: historical climate persistence preparation

Status: HISTORICAL_PERSISTENCE_PREPARATION_BLOCKED.

The recovered acquisition output is retained under data/reports and its original SHA-256 values are compared with current files in stage12_4b5_source_provenance.json. The offline quality report covers 28 source files and seven parameters. A 2010–2025 sample includes 5,844 distinct dates. Missing-value and physically implausible-value counts are reported independently of date coverage.

The 2024 pilot and the two historical batches must remain separate dataset versions. Downstream climatology must select exactly one version for overlapping sample/date combinations; never sum pilot and historical observations as independent evidence. District representative samples are coarse grid estimates, not exact attraction-level climate measurements.

The scope/checksum dry-run does not test SQL execution, checkpointing, rollback or idempotency. The historical write path is deliberately disabled. An isolated PostgreSQL transaction test and a reviewed response to the recorded 2.41 versus actual 2.31 collation mismatch remain prerequisites. Rebuild affected indexes only after backup verification, isolation testing and explicit maintenance authorization; no maintenance was performed here.

No NASA requests, historical database writes, Qdrant writes, or ranking changes were made in this stage.
