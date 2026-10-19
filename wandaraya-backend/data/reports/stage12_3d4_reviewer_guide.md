# Stage 12.3D.4 independent relevance review guide

Review each attraction against the query's interests and travel date using only
the factual material visible in your blinded CSV. Do not infer a score from
row order, do not look up experimental reports, and do not compare answers
with the other reviewer before both files are complete.

## Scale

| Score | Meaning |
| --- | --- |
| 0 | Irrelevant: it does not plausibly serve the stated tourism request. |
| 1 | Weakly relevant: there is a loose connection, but the primary purpose, category, or location is a poor fit. |
| 2 | Relevant: it reasonably supports a material part of the request. |
| 3 | Highly relevant: it directly and strongly fits the stated interests and any supported location constraint. |

Use `cannot_judge=true` only when the factual information in the row is too
limited to make a defensible relevance judgment. Do not use it simply because
the attraction is unfamiliar.

## What to consider

- Match the attraction's stated category/activity to the stated interests.
- Treat an explicit district preference as meaningful when a district is shown.
- Use the date only when the CSV presents factual context for it.
- Do not award an event-related advantage merely because an event exists on the
  date: no event-to-attraction link is verified at this stage.
- Unknown metadata is unknown, not evidence for or against relevance.

## What not to edit

Do not change IDs, names, dates, categories, activities, `reviewer_id`, or the
query text. Complete only `cannot_judge`, `relevance_0_to_3`, and optionally
`reviewer_explanation`.
