# Stage 12.4B.2 — Climate Persistence and Backfill Plan

The six NASA POWER pilot files passed checksum and dry-run validation for 2,196
daily observations. The climate migration remains unapplied to `wandaraya`.

An isolated migration test was attempted using a temporary clone of the active
database. PostgreSQL refused the clone because `wandaraya` has a collation
version mismatch. This is an infrastructure blocker, not a climate-data error.
No test database was created and no live database schema/data was changed.

The future 2010–2025 plan begins with 25 district representative samples
(one bounded request each; 146,100 structural daily sample records), preserving
raw responses, checkpoints and per-response validation. It is a plan only;
no national acquisition has run.
