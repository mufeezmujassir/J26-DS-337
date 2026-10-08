from sqlalchemy import select

from app.models.weather_station import WeatherStation


class WeatherStationLoader:

    @staticmethod
    async def upsert(
        db,
        station_data: dict,
    ) -> WeatherStation:

        stmt = select(
            WeatherStation
        ).where(
            WeatherStation.station_id
            == station_data["station_id"]
        )

        result = await db.execute(stmt)

        station = result.scalar_one_or_none()

        if station is None:

            station = WeatherStation(
                station_id=station_data[
                    "station_id"
                ],
                station_name=station_data[
                    "station_name"
                ],
                latitude=station_data.get(
                    "latitude"
                ),
                longitude=station_data.get(
                    "longitude"
                ),
                district_id=station_data.get(
                    "district_id"
                ),
                has_rainfall=station_data[
                    "has_rainfall"
                ],
                has_temperature=station_data[
                    "has_temperature"
                ],
            )

            db.add(station)

        else:

            station.station_name = (
                station_data["station_name"]
            )

            # Blank metadata must not erase coordinates previously verified and
            # stored in the canonical station registry.
            if station_data.get("latitude") is not None:
                station.latitude = station_data["latitude"]

            if station_data.get("longitude") is not None:
                station.longitude = station_data["longitude"]

            station.has_rainfall = (
                station_data["has_rainfall"]
            )

            station.has_temperature = (
                station_data[
                    "has_temperature"
                ]
            )

            if station_data.get(
                "district_id"
            ) is not None:
                station.district_id = (
                    station_data[
                        "district_id"
                    ]
                )

        await db.flush()

        return station
