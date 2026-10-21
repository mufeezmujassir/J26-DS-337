# Stage 12.4F Diagnostics and Model Refinement

Stage 12.4F is completed with limitations. The 52 queries are an inspected benchmark. Fixed candidates are exploratory; the calibrated blend uses grouped cross-validation with every attraction-activity query and its 12 months kept together. Thirteen climate-source clusters are too few for strong selection claims. District multivariable remains the best-supported reference; no refined candidate is approved for production.
{
  "status": "GROUPED_CROSS_VALIDATION_EXPLORATORY",
  "grouping_unit": "climate-source identity; all 12 months of a query remain together",
  "clusters": 13,
  "folds": [
    {
      "fold": 1,
      "activity_weight": 0.25,
      "train_queries": 40,
      "test_queries": 12,
      "test_clusters": [
        "3:DISTRICT_REPRESENTATIVE_PROXY:Ampara",
        "3:DISTRICT_REPRESENTATIVE_PROXY:Hambantota",
        "3:DISTRICT_REPRESENTATIVE_PROXY:Moneragala"
      ]
    },
    {
      "fold": 2,
      "activity_weight": 0.25,
      "train_queries": 42,
      "test_queries": 10,
      "test_clusters": [
        "3:DISTRICT_REPRESENTATIVE_PROXY:Badulla",
        "3:DISTRICT_REPRESENTATIVE_PROXY:Kalutara",
        "3:DISTRICT_REPRESENTATIVE_PROXY:Nuwara Eliya"
      ]
    },
    {
      "fold": 3,
      "activity_weight": 0.25,
      "train_queries": 39,
      "test_queries": 13,
      "test_clusters": [
        "3:DISTRICT_REPRESENTATIVE_PROXY:Colombo",
        "3:DISTRICT_REPRESENTATIVE_PROXY:Kandy",
        "3:DISTRICT_REPRESENTATIVE_PROXY:Ratnapura"
      ]
    },
    {
      "fold": 4,
      "activity_weight": 0.25,
      "train_queries": 43,
      "test_queries": 9,
      "test_clusters": [
        "3:DISTRICT_REPRESENTATIVE_PROXY:Galle",
        "3:DISTRICT_REPRESENTATIVE_PROXY:Kegalle"
      ]
    },
    {
      "fold": 5,
      "activity_weight": 0.0,
      "train_queries": 44,
      "test_queries": 8,
      "test_clusters": [
        "3:DISTRICT_REPRESENTATIVE_PROXY:Gampaha",
        "3:DISTRICT_REPRESENTATIVE_PROXY:Matara"
      ]
    }
  ],
  "leakage_check": true,
  "rankable_queries": 52,
  "incomplete_queries_excluded": 8,
  "insufficient_records_preserved_missing": 96,
  "metrics": {
    "ndcg@3": {
      "mean": 0.8873369502315217,
      "valid_queries": 52
    },
    "ndcg@5": {
      "mean": 0.9139929193700433,
      "valid_queries": 52
    },
    "ndcg@12": {
      "mean": 0.9589390976271578,
      "valid_queries": 52
    },
    "spearman": {
      "mean": 0.7950431875606414,
      "valid_queries": 52
    },
    "kendall_tau_b": {
      "mean": 0.7010080509661519,
      "valid_queries": 52
    },
    "top3_overlap": {
      "mean": 0.673076923076923,
      "valid_queries": 52
    },
    "mrr_grade_ge_3": {
      "mean": 0.9039007092198581,
      "valid_queries": 47
    }
  },
  "limitation": "The same evaluated benchmark supplies model-selection folds; this is cross-validated exploration, not fresh independent confirmation."
}
