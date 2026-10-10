from app.database import Base
from app.models.data_sources import DataSource
from app.models.district import District
from app.models.categories import Category
from app.models.activities import Activity
from app.models.attraction import Attraction
from app.models.attraction_categories import AttractionCategory
from app.models.attraction_activities import AttractionActivity
from app.models.attraction_descriptions import AttractionDescription
from app.models.attraction_reviews import AttractionReview
from app.models.attraction_images import AttractionImage
from app.models.holiday_calendar import Holiday
from app.models.user import User
from app.models.group import TripGroup, GroupMember
from app.models.weather_station import WeatherStation
from app.models.weather_reading import WeatherReading
from app.models.district_weather_monthly import DistrictWeatherMonthly
from app.models.weather_model_run import WeatherModelRun
from app.models.weather_forecast import WeatherForecast

# Removed weather models, user_preference, and group_preference per user instruction.

__all__ = [
    "Base",
    "DataSource",
    "District",
    "Category",
    "Activity",
    "Attraction",
    "AttractionCategory",
    "AttractionActivity",
    "AttractionDescription",
    "AttractionReview",
    "AttractionImage",
    "Holiday",
    "User",
    "TripGroup",
    "GroupMember",
    "WeatherStation",
    "WeatherReading",
    "DistrictWeatherMonthly",
    "WeatherModelRun",
    "WeatherForecast",
]
