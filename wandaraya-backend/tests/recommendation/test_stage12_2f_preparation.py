from app.recommendation.evaluation.stage12_2f import QUERY_SPECS, blinded_order


def test_ten_preserved_query_ids_are_unique():
    assert len(QUERY_SPECS) == 10
    assert len({row["query_id"] for row in QUERY_SPECS}) == 10
    assert QUERY_SPECS[0]["query_id"] == "q01_galle_heritage"


def test_blinded_order_is_stable_and_does_not_equal_rank():
    assert blinded_order("q01_galle_heritage", 1) == blinded_order("q01_galle_heritage", 1)
    assert blinded_order("q01_galle_heritage", 1) != blinded_order("q01_galle_heritage", 2)
