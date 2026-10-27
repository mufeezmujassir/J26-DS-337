from app.agents.recommendation_graph.nodes.handlers import _weather_rejection


def candidate(*, name="Unawatuna Beach", source="openweathermap", probability=1.0,
              rainfall=32.0, descriptions=None, categories=None, activities=None):
    return {
        "attraction_id": 10,
        "attraction_name": name,
        "city": "Galle",
        "district_name": "Galle",
        "categories": categories or ["Beaches & Coastal"],
        "activities": activities or ["Swimming"],
        "evidence": {
            "weather": {
                "status": "AVAILABLE",
                "details": {
                    "conditions": {
                        "actual_source": source,
                        "precipitation_probability_max": probability,
                        "rainfall_mm": rainfall,
                        "provenance": {
                            "weather_descriptions": descriptions or ["moderate rain"]
                        },
                    }
                },
            }
        },
    }


def test_live_rain_rejects_outdoor_candidate_with_explanation():
    result = _weather_rejection(candidate())
    assert result is not None
    assert "100% precipitation probability" in result["weather_summary"]
    assert "Prefer a sheltered or indoor alternative" in result["reason"]


def test_monthly_planning_weather_never_rejects_a_specific_day():
    assert _weather_rejection(candidate(source="approved_model")) is None


def test_indoor_museum_is_not_rejected_during_rain():
    item = candidate(
        name="Galle Museum",
        categories=["Culture & Heritage"],
        activities=["Museum Visit"],
    )
    assert _weather_rejection(item) is None


def test_plant_nursery_is_treated_as_outdoor_during_live_rain():
    item = candidate(
        name="Ratna Plant Nursery",
        categories=["Tea, Agriculture & Plantation"],
        activities=[],
    )
    assert _weather_rejection(item) is not None


def test_outdoor_monument_is_not_misclassified_as_indoor_museum():
    item = candidate(
        name="War Heroes Memorial Monument",
        categories=["History & Archaeology"],
        activities=["Museum Visit", "Sightseeing"],
    )
    assert _weather_rejection(item) is not None
