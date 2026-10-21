# Stage 12.4E.1 Baseline and Ablation Methods

Baselines A–C reproduce persisted Stage 12.4C ranks/scores: ascending median rainfall, the original 0.45/0.25/0.15/0.15 multivariable composite, and ascending rainfall mean plus 0.5 standard deviation. Method D reproduces frozen Stage 12.4D scores. Ties use ascending calendar month.

Ablations remove one stored normalized contribution and renormalize remaining non-zero activity weights. The generic-weight ablation uses Stage 12.4C multivariable weights. District-only substitutes district features. Wind removal is unavailable because production profiles assign wind zero weight. No persisted production score or weight is changed.
