"""Sample realistic disruption scenarios from the raw public data sources.

Four of the thirteen model features are grounded in real data:

* ``rain_duration_hours`` and ``rain_intensity_score`` -- derived from the real
  monthly rainfall of the attraction's district;
* ``temperature_celsius`` and ``heat_warning`` -- derived from the real monthly
  maximum temperature;
* ``is_outdoor_activity`` -- taken from the real attraction record.

The remaining signals (closures, crowds, complaints, GPS drift, delays and the
number of affected activities) are not observable in the raw sources and are
sampled with a seeded RNG.  Only attractions whose district has weather
coverage are eligible, which keeps ``real_data_ratio`` at 1.0.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.replanning.disruption_detection.classifiers._dataset_io import load_jsonl

LOGGER = logging.getLogger(__name__)

# Heuristic conversion from a real daily rainfall amount to hours of rain.
# ~4 mm of rainfall per hour corresponds to moderate rain.
RAIN_MM_PER_HOUR = 4.0
MAX_RAIN_HOURS = 8.0
DAYS_PER_MONTH: Tuple[int, ...] = (
    31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31,
)

# A recorded maximum temperature at or below this value is treated as missing.
MIN_VALID_TEMP = 0.0
HEAT_WARNING_THRESHOLD = 35.0

# Probabilities / ranges for the signals that cannot be observed in the raw
# sources. The "trigger" probability of each signal is kept small so the
# emergent label mix approximates the 40/30/20/10 target.
CLOSURE_PROBABILITY = 0.10
CAPACITY_PROBABILITY = 0.12
COMPLAINT_PROBABILITY = 0.15
CHANGE_REQUEST_PROBABILITY = 0.10
GPS_TRIGGER_PROBABILITY = 0.10
DELAY_TRIGGER_PROBABILITY = 0.10

COMPLAINT_THRESHOLD = 0.70
GPS_THRESHOLD_KM = 5.0
DELAY_THRESHOLD_MIN = 60

# Weighted distribution for the number of affected activities (0-5). Keeps the
# plan-level rule from dominating while still supplying enough positive cases.
_AFFECTED_CHOICES = (0, 1, 2, 3, 4, 5)
_AFFECTED_WEIGHTS = (40, 28, 20, 6, 4, 2)


class FeatureSampler:
    """Draw realistic scenarios from the raw attraction + weather sources."""

    def __init__(
        self,
        attractions_path: str | Path,
        weather_path: str | Path,
        seed: int = 42,
    ) -> None:
        self.attractions_path = Path(attractions_path)
        self.weather_path = Path(weather_path)
        self.seed = int(seed)
        self._rng = random.Random(seed)

        self.attractions: List[Dict[str, Any]] = []
        self.weather: List[Dict[str, Any]] = []
        self.sampleable_attractions: List[Dict[str, Any]] = []

        self._weather_index: Dict[Tuple[int, int], Dict[str, float]] = {}
        self._district_names: Dict[int, str] = {}
        self._rain_min = 0.0
        self._rain_max = 1.0
        self._mean_rainfall = 0.0
        self._mean_temperature = 30.0

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_sources(self) -> None:
        """Load both raw sources and build the lookup indexes."""
        self.attractions = load_jsonl(self.attractions_path)
        self.weather = load_jsonl(self.weather_path)
        LOGGER.info(
            "Loaded %d attractions and %d weather records",
            len(self.attractions),
            len(self.weather),
        )

        self._build_weather_index()
        self._build_district_names()
        self._select_sampleable_attractions()

    def _build_weather_index(self) -> None:
        accum: Dict[Tuple[int, int], Dict[str, List[float]]] = {}
        rainfalls: List[float] = []
        temperatures: List[float] = []

        for record in self.weather:
            district_id = int(record["district_id"])
            month = int(record["month"])
            rainfall = float(record.get("rainfall_mm", 0.0))
            temp_max = float(record.get("temp_max_c", 0.0))

            key = (district_id, month)
            bucket = accum.setdefault(key, {"rain": [], "temp": []})
            bucket["rain"].append(rainfall)
            rainfalls.append(rainfall)
            if temp_max > MIN_VALID_TEMP:
                bucket["temp"].append(temp_max)
                temperatures.append(temp_max)

        self._weather_index = {}
        for key, bucket in accum.items():
            rain = sum(bucket["rain"]) / len(bucket["rain"])
            if bucket["temp"]:
                temp = sum(bucket["temp"]) / len(bucket["temp"])
            else:  # pragma: no cover - only if every year is invalid
                temp = self._mean_temperature
            self._weather_index[key] = {
                "rainfall_mm": rain,
                "temp_max_c": temp,
            }

        if rainfalls:
            self._rain_min = min(rainfalls)
            self._rain_max = max(rainfalls)
            self._mean_rainfall = sum(rainfalls) / len(rainfalls)
        if temperatures:
            self._mean_temperature = sum(temperatures) / len(temperatures)

        LOGGER.info(
            "Weather index covers %d (district, month) cells",
            len(self._weather_index),
        )

    def _build_district_names(self) -> None:
        names: Dict[int, str] = {}
        for attraction in self.attractions:
            district_id = int(attraction["district_id"])
            name = str(attraction.get("district") or "").strip()
            if name and district_id not in names:
                names[district_id] = name
        self._district_names = names

    def _select_sampleable_attractions(self) -> None:
        covered = {district_id for district_id, _ in self._weather_index}
        selected = [
            attraction
            for attraction in self.attractions
            if int(attraction["district_id"]) in covered
        ]
        if not selected:  # pragma: no cover - defensive
            raise ValueError(
                "No attractions overlap with the weather district coverage; "
                f"check {self.attractions_path} and {self.weather_path}."
            )
        self.sampleable_attractions = selected
        LOGGER.info(
            "%d/%d attractions fall inside a weather-covered district",
            len(selected),
            len(self.attractions),
        )

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def _normalised_rain_intensity(self, rainfall: float) -> float:
        span = self._rain_max - self._rain_min
        if span <= 0.0:
            return 0.0
        score = (rainfall - self._rain_min) / span
        return round(min(1.0, max(0.0, score)), 4)

    def sample_scenario(self) -> Dict[str, Any]:
        """Draw one scenario combining real weather/attraction + noise signals."""
        attraction = self._rng.choice(self.sampleable_attractions)
        district_id = int(attraction["district_id"])
        month = self._rng.randint(1, 12)

        weather = self._weather_index.get((district_id, month))
        is_real_weather = weather is not None
        if weather is None:  # pragma: no cover - guarded by selection
            rainfall = self._mean_rainfall
            temp_max = self._mean_temperature
        else:
            rainfall = weather["rainfall_mm"]
            temp_max = weather["temp_max_c"]

        daily_rain = rainfall / DAYS_PER_MONTH[month - 1]
        rain_duration = round(
            min(MAX_RAIN_HOURS, daily_rain / RAIN_MM_PER_HOUR), 4
        )
        heat_warning = 1 if temp_max > HEAT_WARNING_THRESHOLD else 0

        # Bounded mixtures keep the "trigger" signals realistic while limiting
        # how often each rule fires.
        if self._rng.random() < COMPLAINT_PROBABILITY:
            complaint_score = round(
                self._rng.uniform(COMPLAINT_THRESHOLD + 0.01, 1.0), 4
            )
        else:
            complaint_score = round(
                self._rng.uniform(0.0, COMPLAINT_THRESHOLD), 4
            )

        if self._rng.random() < GPS_TRIGGER_PROBABILITY:
            gps_deviation = self._rng.uniform(GPS_THRESHOLD_KM + 0.1, 12.0)
        else:
            gps_deviation = self._rng.uniform(0.0, GPS_THRESHOLD_KM)

        if self._rng.random() < DELAY_TRIGGER_PROBABILITY:
            delay = self._rng.randint(DELAY_THRESHOLD_MIN + 1, 120)
        else:
            delay = self._rng.randint(0, DELAY_THRESHOLD_MIN)

        scenario: Dict[str, Any] = {
            "rain_duration_hours": rain_duration,
            "rain_intensity_score": self._normalised_rain_intensity(rainfall),
            "temperature_celsius": round(temp_max, 1),
            "heat_warning": heat_warning,
            "is_outdoor_activity": 1 if attraction.get("is_outdoor") else 0,
            "closure_flag": 1 if self._rng.random() < CLOSURE_PROBABILITY else 0,
            "capacity_issue": (
                1 if self._rng.random() < CAPACITY_PROBABILITY else 0
            ),
            "crowd_level_score": round(self._rng.random(), 4),
            "complaint_score": complaint_score,
            "change_request": (
                1 if self._rng.random() < CHANGE_REQUEST_PROBABILITY else 0
            ),
            "gps_deviation_km": round(gps_deviation, 3),
            "time_delay_minutes": delay,
            "num_affected_activities": self._rng.choices(
                _AFFECTED_CHOICES, weights=_AFFECTED_WEIGHTS, k=1
            )[0],
            # Provenance (not part of the feature vector).
            "attraction_id": attraction.get("attraction_id"),
            "attraction_name": attraction.get("name"),
            "district": self._district_names.get(district_id, ""),
            "district_id": district_id,
            "category": attraction.get("category"),
            "month": month,
            "is_real_weather": is_real_weather,
            "is_real_attraction": True,
        }
        return scenario

    def sample_batch(self, num_rows: int) -> List[Dict[str, Any]]:
        """Draw ``num_rows`` scenarios in a deterministic order."""
        return [self.sample_scenario() for _ in range(num_rows)]


__all__ = ["FeatureSampler"]
