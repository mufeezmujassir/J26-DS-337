import argparse
from datetime import date

from app.weather_model.context.climatology_provider import ClimatologyProvider


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument(
        "--district-id",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--travel-date",
        type=date.fromisoformat,
        required=True,
    )

    parser.add_argument(
        "--data-root",
        default="data/weather/modeling/prophet",
    )

    args = parser.parse_args()

    provider = ClimatologyProvider(
        data_root=args.data_root,
        min_years=3,
    )

    result = provider.get_climatology(
        district_id=args.district_id,
        travel_date=args.travel_date,
    )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()