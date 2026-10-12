"""Print pilot activity scores for the verified Galle live-weather example."""

from datetime import date

from app.weather_model.suitability.schemas import WeatherSuitabilityInput
from app.weather_model.suitability.scorer import WeatherSuitabilityScorer


def main() -> None:
    activities = [
        "hiking",
        "beach",
        "wildlife_safari",
        "cultural_outdoor",
        "water_activities",
        "indoor_museum",
    ]

    for activity in activities:
        result = WeatherSuitabilityScorer.score(
            WeatherSuitabilityInput(
                district_id=78,
                travel_date=date(2026, 10, 13),
                activity_type=activity,
                weather_source="openweathermap",
                rainfall_mm=2.19,
                rainfall_period="available_3h_intervals",
                temperature_min_c=26.9,
                temperature_max_c=30.23,
                precipitation_probability_max=0.98,
            )
        )
        print(
            f"{activity}: score={result.score}, "
            f"suitability={result.suitability}, "
            f"confidence={result.confidence}"
        )


if __name__ == "__main__":
    main()
