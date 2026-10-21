# Stage 12.4D.2 Evidence Reconciliation and Evaluation Freeze

Status: dataset frozen under `stage12_4d2_eval_v1` with evidence policy `12.4d2_v1.2`.

Direct SQL confirmed Result A as the Stage 12.4D.1 persisted snapshot before this stage: 10,127 mappings, 8,940 eligible, 1,187 unsupported, 107,280 active profiles, and status counts 1,023 VERIFIED / 3,189 SUPPORTED_INFERRED / 4,728 PROVISIONAL / 1,187 UNSUPPORTED. Result B appears in narrative material but is not supported by the current database or timestamped final/readback JSON. Its precise originating run or code version cannot be established and remains explicitly unresolved.

Evidence policy v1.2 separates source strength, rule validation, independent review, and offline-evaluation eligibility. Tier A means explicit structured evidence; it does not mean human verification. Tier B is deterministic inference. Tier C is weak context. Tier D is absent or contradictory. Provisional mappings remain available for uncertainty analysis and are not positive primary ground truth.

The frozen monthly dataset includes only active profiles whose mappings are offline-evaluation eligible. Rows are deterministically sorted and serialized, and every export has a SHA-256 digest. No missing climate value was synthetically filled. Reviewer templates are blank and model conclusions are withheld.

Scientific limitations remain: independent labels are pending; deterministic rules and mappings are dependent evidence; many profiles share district proxies; NASA POWER resolution does not capture all local microclimates; and the evaluation assesses historical relative climate favorability, not live safety or operational availability.
