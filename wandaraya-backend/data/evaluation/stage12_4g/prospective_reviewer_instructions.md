# Stage 12.4G Independent Reviewer Instructions

Dataset: `stage12_4g_prospective_review_v1`. Review all 864 month items independently without consulting another reviewer. Examine the supplied source references and any source-backed evidence you actually use. Do not infer a label from the ordering of rows; no model or baseline prediction is present.

Fill `reviewer_id`, `reviewer_expertise`, an ISO-8601 `review_timestamp`, `evidence_reviewed`, `decision`, `confidence`, and `notes`. Decisions are `VERY_FAVORABLE`, `FAVORABLE`, `NEUTRAL`, `UNFAVORABLE`, `VERY_UNFAVORABLE`, or `INSUFFICIENT_EVIDENCE`. Use insufficient evidence when the attraction-activity relationship or monthly evidence cannot support a defensible grade; it remains missing, never zero. Each of two reviewers must work from a separate copy. Disagreements require a separate human adjudicator and must not be automatically resolved.
