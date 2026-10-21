# Stage 12.4F Diagnostics and Model Refinement

Stage 12.4F is completed with limitations. The 52 queries are an inspected benchmark. Fixed candidates are exploratory; the calibrated blend uses grouped cross-validation with every attraction-activity query and its 12 months kept together. Thirteen climate-source clusters are too few for strong selection claims. District multivariable remains the best-supported reference; no refined candidate is approved for production.
{
  "status": "EXPLORATORY_BENCHMARK_COMPARISON",
  "ground_truth": "stage12_4e2_ground_truth_v1",
  "candidates": {
    "A_activity_aware": {
      "metrics": {
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
      "mean_ndcg5_difference_vs_district": -0.018674752878607984,
      "cluster_bootstrap_difference": {
        "status": "COMPUTED",
        "clusters": 13,
        "iterations": 10000,
        "seed": 12403,
        "mean": -0.019608035039586556,
        "ci95": [
          -0.046491217976537075,
          0.0036118651654334206
        ]
      },
      "mean_latency_ms_per_query": 0.003184230769230769,
      "coverage": 1.0,
      "mean_unique_month_scores": 11.98076923076923
    },
    "B_district_multivariable": {
      "metrics": {
        "ndcg@3": {
          "mean": 0.8894207906636161,
          "valid_queries": 52
        },
        "ndcg@5": {
          "mean": 0.9157434177595347,
          "valid_queries": 52
        },
        "ndcg@12": {
          "mean": 0.9605021490470987,
          "valid_queries": 52
        },
        "spearman": {
          "mean": 0.7971455430414155,
          "valid_queries": 52
        },
        "kendall_tau_b": {
          "mean": 0.7042640361844815,
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
      "mean_ndcg5_difference_vs_district": 0.0,
      "cluster_bootstrap_difference": {
        "status": "COMPUTED",
        "clusters": 13,
        "iterations": 10000,
        "seed": 12403,
        "mean": 0.0,
        "ci95": [
          0.0,
          0.0
        ]
      },
      "mean_latency_ms_per_query": 0.003184230769230769,
      "coverage": 1.0,
      "mean_unique_month_scores": 12
    },
    "C_activity_weighting_disabled": {
      "metrics": {
        "ndcg@3": {
          "mean": 0.8938520237825179,
          "valid_queries": 52
        },
        "ndcg@5": {
          "mean": 0.914137825551812,
          "valid_queries": 52
        },
        "ndcg@12": {
          "mean": 0.9577313066035684,
          "valid_queries": 52
        },
        "spearman": {
          "mean": 0.802241096550058,
          "valid_queries": 52
        },
        "kendall_tau_b": {
          "mean": 0.7073681426187305,
          "valid_queries": 52
        },
        "top3_overlap": {
          "mean": 0.6602564102564102,
          "valid_queries": 52
        },
        "mrr_grade_ge_3": {
          "mean": 0.8914893617021277,
          "valid_queries": 47
        }
      },
      "mean_ndcg5_difference_vs_district": -0.0016055922077227213,
      "cluster_bootstrap_difference": {
        "status": "COMPUTED",
        "clusters": 13,
        "iterations": 10000,
        "seed": 12403,
        "mean": -0.002034713730664429,
        "ci95": [
          -0.013322828964513393,
          0.0062659104249186874
        ]
      },
      "mean_latency_ms_per_query": 0.003184230769230769,
      "coverage": 1.0,
      "mean_unique_month_scores": 12
    },
    "D_reduced_activity_weight_strength": {
      "metrics": {
        "ndcg@3": {
          "mean": 0.8921974614264234,
          "valid_queries": 52
        },
        "ndcg@5": {
          "mean": 0.9104700031874828,
          "valid_queries": 52
        },
        "ndcg@12": {
          "mean": 0.9540990999044852,
          "valid_queries": 52
        },
        "spearman": {
          "mean": 0.7952335155951684,
          "valid_queries": 52
        },
        "kendall_tau_b": {
          "mean": 0.6999927163521336,
          "valid_queries": 52
        },
        "top3_overlap": {
          "mean": 0.6666666666666666,
          "valid_queries": 52
        },
        "mrr_grade_ge_3": {
          "mean": 0.8868794326241135,
          "valid_queries": 47
        }
      },
      "mean_ndcg5_difference_vs_district": -0.0052734145720518205,
      "cluster_bootstrap_difference": {
        "status": "COMPUTED",
        "clusters": 13,
        "iterations": 10000,
        "seed": 12403,
        "mean": -0.00594501781027661,
        "ci95": [
          -0.024726477855423996,
          0.008165387976656103
        ]
      },
      "mean_latency_ms_per_query": 0.003184230769230769,
      "coverage": 1.0,
      "mean_unique_month_scores": 12
    },
    "E_evidence_confidence_aware": {
      "metrics": {
        "ndcg@3": {
          "mean": 0.8939691633602111,
          "valid_queries": 52
        },
        "ndcg@5": {
          "mean": 0.9043857637004628,
          "valid_queries": 52
        },
        "ndcg@12": {
          "mean": 0.9548661283120334,
          "valid_queries": 52
        },
        "spearman": {
          "mean": 0.7937295789757964,
          "valid_queries": 52
        },
        "kendall_tau_b": {
          "mean": 0.6973113887133684,
          "valid_queries": 52
        },
        "top3_overlap": {
          "mean": 0.6666666666666666,
          "valid_queries": 52
        },
        "mrr_grade_ge_3": {
          "mean": 0.9074468085106383,
          "valid_queries": 47
        }
      },
      "mean_ndcg5_difference_vs_district": -0.011357654059071961,
      "cluster_bootstrap_difference": {
        "status": "COMPUTED",
        "clusters": 13,
        "iterations": 10000,
        "seed": 12403,
        "mean": -0.012167170094608246,
        "ci95": [
          -0.03378804032926724,
          0.006833022862923938
        ]
      },
      "mean_latency_ms_per_query": 0.003184230769230769,
      "coverage": 1.0,
      "mean_unique_month_scores": 12
    },
    "F_fixed_calibrated_blend": {
      "metrics": {
        "ndcg@3": {
          "mean": 0.890187602198451,
          "valid_queries": 52
        },
        "ndcg@5": {
          "mean": 0.916132200838211,
          "valid_queries": 52
        },
        "ndcg@12": {
          "mean": 0.9607609293983209,
          "valid_queries": 52
        },
        "spearman": {
          "mean": 0.7969297007424043,
          "valid_queries": 52
        },
        "kendall_tau_b": {
          "mean": 0.7030949307606046,
          "valid_queries": 52
        },
        "top3_overlap": {
          "mean": 0.673076923076923,
          "valid_queries": 52
        },
        "mrr_grade_ge_3": {
          "mean": 0.9109929078014184,
          "valid_queries": 47
        }
      },
      "mean_ndcg5_difference_vs_district": 0.00038878307867637463,
      "cluster_bootstrap_difference": {
        "status": "COMPUTED",
        "clusters": 13,
        "iterations": 10000,
        "seed": 12403,
        "mean": 0.0002496887209457323,
        "ci95": [
          -0.0038704141934788622,
          0.005280467886951468
        ]
      },
      "mean_latency_ms_per_query": 0.003184230769230769,
      "coverage": 1.0,
      "mean_unique_month_scores": 12
    },
    "G_conservative_adjustment": {
      "metrics": {
        "ndcg@3": {
          "mean": 0.8888461052607232,
          "valid_queries": 52
        },
        "ndcg@5": {
          "mean": 0.9152307444365736,
          "valid_queries": 52
        },
        "ndcg@12": {
          "mean": 0.9596710230642055,
          "valid_queries": 52
        },
        "spearman": {
          "mean": 0.7934856293987277,
          "valid_queries": 52
        },
        "kendall_tau_b": {
          "mean": 0.6988334582809601,
          "valid_queries": 52
        },
        "top3_overlap": {
          "mean": 0.673076923076923,
          "valid_queries": 52
        },
        "mrr_grade_ge_3": {
          "mean": 0.9104863221884498,
          "valid_queries": 47
        }
      },
      "mean_ndcg5_difference_vs_district": -0.0005126733229610253,
      "cluster_bootstrap_difference": {
        "status": "COMPUTED",
        "clusters": 13,
        "iterations": 10000,
        "seed": 12403,
        "mean": -0.0005915836033761276,
        "ci95": [
          -0.002824244243456483,
          0.0010718077752052552
        ]
      },
      "mean_latency_ms_per_query": 0.003184230769230769,
      "coverage": 1.0,
      "mean_unique_month_scores": 12
    },
    "F_grouped_cv_calibrated_blend": {
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
      "mean_ndcg5_difference_vs_district": -0.001750498389491345,
      "cluster_bootstrap_difference": {
        "status": "COMPUTED",
        "clusters": 13,
        "iterations": 10000,
        "seed": 12403,
        "mean": -0.0018195522030919474,
        "ci95": [
          -0.004233763546676742,
          0.0
        ]
      },
      "mean_latency_ms_per_query": 0.01,
      "coverage": 1.0,
      "mean_unique_month_scores": 12
    }
  },
  "selection": "B_district_multivariable_retained_as_best_supported_reference",
  "selection_reason": "Highest pre-existing human benchmark mean and lower complexity; no refinement is independently confirmed.",
  "production_approval": false
}
