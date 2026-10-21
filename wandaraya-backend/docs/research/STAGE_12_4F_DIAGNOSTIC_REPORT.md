# Stage 12.4F Diagnostics and Model Refinement

Stage 12.4F is completed with limitations. The 52 queries are an inspected benchmark. Fixed candidates are exploratory; the calibrated blend uses grouped cross-validation with every attraction-activity query and its 12 months kept together. Thirteen climate-source clusters are too few for strong selection claims. District multivariable remains the best-supported reference; no refined candidate is approved for production.
{
  "status": "COMPUTED",
  "alembic_head": "h45c6d7e8f9a",
  "rankable_queries": 52,
  "clusters": 13,
  "months": 624,
  "activity_weight_profile": {
    "profiles": 16,
    "mean_largest_weight": 0.41875,
    "max_largest_weight": 0.5,
    "interpretation": "Large activity-specific weights materially change ordering, but causal over-aggressiveness is not proven."
  },
  "mapping_inventory": [
    {
      "tier": "A",
      "status": "PROVISIONAL",
      "count": 40
    },
    {
      "tier": "B",
      "status": "PROVISIONAL",
      "count": 151
    },
    {
      "tier": "A",
      "status": "SUPPORTED_INFERRED",
      "count": 244
    },
    {
      "tier": "B",
      "status": "SUPPORTED_INFERRED",
      "count": 2945
    },
    {
      "tier": "D",
      "status": "UNSUPPORTED",
      "count": 1229
    },
    {
      "tier": "A",
      "status": "VERIFIED",
      "count": 1023
    },
    {
      "tier": "C",
      "status": "PROVISIONAL",
      "count": 4495
    }
  ],
  "cohort_performance": {
    "A": {
      "ndcg@3": {
        "mean": 0.8669536194093475,
        "valid_queries": 39
      },
      "ndcg@5": {
        "mean": 0.8872897141812142,
        "valid_queries": 39
      },
      "ndcg@12": {
        "mean": 0.9437921023889448,
        "valid_queries": 39
      },
      "spearman": {
        "mean": 0.7895387132576154,
        "valid_queries": 39
      },
      "kendall_tau_b": {
        "mean": 0.6921271551267901,
        "valid_queries": 39
      },
      "top3_overlap": {
        "mean": 0.6495726495726496,
        "valid_queries": 39
      },
      "mrr_grade_ge_3": {
        "mean": 0.8967592592592593,
        "valid_queries": 36
      }
    },
    "B": {
      "ndcg@3": {
        "mean": 0.9484034007931305,
        "valid_queries": 13
      },
      "ndcg@5": {
        "mean": 0.9264055169800645,
        "valid_queries": 13
      },
      "ndcg@12": {
        "mean": 0.9729369646639189,
        "valid_queries": 13
      },
      "spearman": {
        "mean": 0.7688806178244525,
        "valid_queries": 13
      },
      "kendall_tau_b": {
        "mean": 0.6740800957547429,
        "valid_queries": 13
      },
      "top3_overlap": {
        "mean": 0.6923076923076923,
        "valid_queries": 13
      },
      "mrr_grade_ge_3": {
        "mean": 0.9272727272727272,
        "valid_queries": 11
      }
    }
  },
  "geographic_performance": {
    "DISTRICT_REPRESENTATIVE_PROXY": {
      "ndcg@3": {
        "mean": 0.8873160647552932,
        "valid_queries": 52
      },
      "ndcg@5": {
        "mean": 0.8970686648809267,
        "valid_queries": 52
      },
      "ndcg@12": {
        "mean": 0.9510783179576884,
        "valid_queries": 52
      },
      "spearman": {
        "mean": 0.7843741893993247,
        "valid_queries": 52
      },
      "kendall_tau_b": {
        "mean": 0.6876153902837784,
        "valid_queries": 52
      },
      "top3_overlap": {
        "mean": 0.6602564102564102,
        "valid_queries": 52
      },
      "mrr_grade_ge_3": {
        "mean": 0.9039007092198581,
        "valid_queries": 47
      }
    },
    "ATTRACTION_COORDINATE_REANALYSIS": {
      "ndcg@3": {
        "mean": null,
        "valid_queries": 0
      },
      "ndcg@5": {
        "mean": null,
        "valid_queries": 0
      },
      "ndcg@12": {
        "mean": null,
        "valid_queries": 0
      },
      "spearman": {
        "mean": null,
        "valid_queries": 0
      },
      "kendall_tau_b": {
        "mean": null,
        "valid_queries": 0
      },
      "top3_overlap": {
        "mean": null,
        "valid_queries": 0
      },
      "mrr_grade_ge_3": {
        "mean": null,
        "valid_queries": 0
      }
    }
  },
  "feature_correlations": {
    "rainfall_sub_index__temperature_comfort": -0.022669129290301945,
    "rainfall_sub_index__humidity_comfort": 0.30211030951745943,
    "rainfall_sub_index__solar_context": 0.4615664708118745,
    "temperature_comfort__humidity_comfort": -0.06970284193916476,
    "temperature_comfort__solar_context": -0.16328242785403901,
    "humidity_comfort__solar_context": 0.5612184847604891
  },
  "missing_feature_rows": {
    "rainfall_cv": 0,
    "rainfall_mean_mm": 0,
    "relative_humidity_mean_pct": 0,
    "solar_radiation_mean_mj": 0,
    "temp_mean_c": 0,
    "wind_speed_mean_ms": 0
  },
  "ablation_query_outperformance_counts": {
    "B_district_multivariable": 11,
    "C_activity_weighting_disabled": 12,
    "D_reduced_activity_weight_strength": 12,
    "E_evidence_confidence_aware": 10,
    "F_fixed_calibrated_blend": 11,
    "G_conservative_adjustment": 11,
    "F_grouped_cv_calibrated_blend": 11
  },
  "diagnostic_findings": [
    "Disabling activity weighting raises benchmark mean NDCG@5 relative to the full model.",
    "District multivariable remains the strongest pre-existing mean benchmark, but its E2 cluster interval versus full crosses zero.",
    "Feature correlations quantify redundancy; they do not by themselves establish harmful double counting.",
    "Coordinate-specific inference remains underpowered."
  ]
}
