# Stage 12.4D.2 Independent Mapping Review Protocol

Dataset version: `stage12_4d2_eval_v1`. Sampling seed: `12402`.

Reviewers must not see model scores, predicted classes, evidence tiers, or rule decisions. Task 1 asks: **Does the available attraction evidence support the proposed activity at this location?** Allowed labels are `SUPPORTED`, `UNSUPPORTED`, `UNCERTAIN`, and `INSUFFICIENT_EVIDENCE`.

Task 2 asks: **Based on the provided independent evidence, how favorable is the specified calendar month for the stated activity at this attraction?** Allowed labels are `VERY_FAVORABLE`, `FAVORABLE`, `NEUTRAL`, `UNFAVORABLE`, `VERY_UNFAVORABLE`, and `INSUFFICIENT_EVIDENCE`.

Record reviewer ID, expertise, timestamp, evidence reviewed, decision, confidence, and notes. Two reviewers should label each item independently; disagreements are adjudicated without revealing model output. Blank fields mean pending review and must never be interpreted as a negative label.

Sampling is deterministic and stratified by activity, historical mapping status, and evidence tier. Sampling probabilities are recorded per mapping. The blind files intentionally omit model-derived conclusions.
