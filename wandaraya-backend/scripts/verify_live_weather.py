"""Print a live OpenWeather forecast aggregate for one explicit location."""

from __future__ import annotations

import argparse
from datetime import date

from app.weather_model.context.live_weather_client import LiveWeatherClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--travel-date", type=date.fromisoformat, required=True)
    arguments = parser.parse_args()

    client = LiveWeatherClient()
    try:
        result = client.get_forecast(
            latitude=arguments.latitude,
            longitude=arguments.longitude,
            travel_date=arguments.travel_date,
        )
    finally:
        client.close()
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
