# Stage 12.4G Sampling and Review Workflow

The prediction-blind inventory contains 8,898 eligible queries. All 60 Stage 12.4E.2 reviewed queries were excluded before selection. Seed `wandaraya-stage12.4g-prospective-v1-20261021` deterministically selected 72 queries / 864 month items across 23 climate-source identities, 21 districts, all 16 climate activity types, tiers A/B/C, 64 district-proxy queries, and 8 genuine coordinate-evidence queries.

Use separate copies of `prospective_reviewer_template.csv` for two genuine independent reviewers. Assign and import with `scripts/manage_stage12_4g_reviews.py`. Required fields include an explicit reviewer ID, expertise, timezone-aware timestamp, evidence actually examined, decision, confidence, and notes. The workflow rejects duplicate reviewer/item submissions, tracks missing reviews, and requires a third independent human for disagreements. No reviewer identity, judgment, or timestamp is prefilled.

The current state is `PENDING_INDEPENDENT_EVIDENCE`: zero prospective judgments exist. Agreement and adjudication statistics therefore remain unavailable.

