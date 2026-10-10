from pathlib import Path

from .rainfall_loader import RainfallLoader
from .temperature_loader import TemperatureLoader


class HistoricalWeatherLoader:

    def __init__(
        self,
        rainfall_file: str | Path,
        rainfall_other_file: str | Path,
        temperature_file: str | Path,
    ):
        self.rainfall_file = rainfall_file
        self.rainfall_other_file = rainfall_other_file
        self.temperature_file = temperature_file

    def load(self):

        rainfall = RainfallLoader.load_combined(
            self.rainfall_file,
            self.rainfall_other_file,
        )

        temperature = TemperatureLoader.load(
            self.temperature_file
        )

        return rainfall, temperature