# Stage 12.4G Execution Instructions

Run from the repository root using the cutover API container:

```text
docker exec -w /app wandaraya-api-cutover python scripts/prepare_stage12_4g_prospective.py
docker exec -w /app wandaraya-api-cutover python scripts/manage_stage12_4g_reviews.py assign --reviewer <REAL_REVIEWER_1_ID>
docker exec -w /app wandaraya-api-cutover python scripts/manage_stage12_4g_reviews.py assign --reviewer <REAL_REVIEWER_2_ID>
```

Each reviewer copies and completes `data/evaluation/stage12_4g/prospective_reviewer_template.csv`; store returned files under `data/evaluation/stage12_4g/completed_reviews/`. Then import and finalize each reviewer:

```text
docker exec -w /app wandaraya-api-cutover python scripts/manage_stage12_4g_reviews.py import --reviewer <ID> --csv /app/data/evaluation/stage12_4g/completed_reviews/<FILE>.csv
docker exec -w /app wandaraya-api-cutover python scripts/manage_stage12_4g_reviews.py finalize --reviewer <ID>
docker exec -w /app wandaraya-api-cutover python scripts/manage_stage12_4g_reviews.py completeness
docker exec -w /app wandaraya-api-cutover python scripts/manage_stage12_4g_reviews.py prepare-adjudication --output /app/data/evaluation/stage12_4g/prospective_adjudication_completed.csv
```

After an independent adjudicator completes that file, import it, run the frozen evaluator, and verify:

```text
docker exec -w /app wandaraya-api-cutover python scripts/manage_stage12_4g_reviews.py import-adjudication --csv /app/data/evaluation/stage12_4g/prospective_adjudication_completed.csv
docker exec -w /app wandaraya-api-cutover python scripts/run_stage12_4g_prospective_evaluation.py
docker exec -w /app wandaraya-api-cutover python scripts/run_stage12_4g_shadow_pilot.py
docker exec -w /app wandaraya-api-cutover python scripts/run_stage12_4g_tests.py
```

Never enable the production reranking flag as part of this workflow.
