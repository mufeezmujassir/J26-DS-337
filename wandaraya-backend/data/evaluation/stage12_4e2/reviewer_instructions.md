# WANDARAYA Stage 12.4E.2 reviewer instructions

Review dataset: `stage12_4e2_review_v1`. Each reviewer receives the full assigned package independently. Do not discuss decisions until both assignments are finalized.

## Mapping task

Judge whether the proposed activity is supported by the attraction evidence. Allowed decisions: `SUPPORTED`, `UNSUPPORTED`, `UNCERTAIN`, `INSUFFICIENT_EVIDENCE`.

## Seasonality task

Judge climate favorability for the named activity and calendar month using only the displayed historical climate evidence. Allowed decisions: `VERY_FAVORABLE`, `FAVORABLE`, `NEUTRAL`, `UNFAVORABLE`, `VERY_UNFAVORABLE`, `INSUFFICIENT_EVIDENCE`.

- `VERY_FAVORABLE` (4): historical conditions are strongly suitable for the named activity.
- `FAVORABLE` (3): conditions are generally suitable, with limited climate drawbacks.
- `NEUTRAL` (2): mixed or moderate conditions provide no clear favorable direction.
- `UNFAVORABLE` (1): conditions present material climate drawbacks.
- `VERY_UNFAVORABLE` (0): conditions are strongly unsuitable on historical climate grounds.
- `INSUFFICIENT_EVIDENCE`: the displayed evidence cannot support a grade; this is not grade zero.

Judge historical seasonal climate suitability, not current operational safety. These averages do not establish swimming, surf, river, flood, landslide, wildlife, or travel safety on a particular day.

For every completed row, supply your assigned `reviewer_id`, expertise, an ISO-8601 `review_timestamp`, what evidence you reviewed, decision, confidence (`LOW`, `MEDIUM`, or `HIGH`), and optional notes. Save partial CSVs freely; import is idempotent and rejects duplicate decisions. Finalization is only allowed after every assigned item has a valid decision. Post-finalization changes require an authorized correction with a reason and preserved history.

Packages intentionally exclude model scores, ranks, classes, evidence tiers, and ablation outputs. Access is operator-managed through the local CLI and database; there is no public review endpoint.
