"""
WANDARAYA Component 2: Fuel Prices & Car Trip Fuel-Cost Estimation Automated Test Suite
========================================================================================
Validates:
1. Ceylon Petroleum Corporation (CEYPETCO) official retail fuel price retrieval and verification.
2. Vehicle fuel-efficiency database models and manufacturer specification provenance.
3. Fuel consumption calculations for both km/L and L/100 km units.
4. One-way and return trip distance calculations (strictly avoiding double-counting).
5. User-entered average fuel-efficiency overrides and uncertainty labeling.
6. Incomplete estimate handling (missing vehicle efficiency, invalid distance, unknown fuel grades).
7. Stale fuel tariff detection and warning alerts.
8. API endpoints contracts:
   - GET  /api/fuel-prices
   - GET  /api/vehicles/fuel-efficiency
   - POST /api/fuel-cost/estimate
   - POST /api/routes/multimodal-plan (enriched car_option and distinct trip_cost_comparison)
"""

import math
import pytest
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.services.fuel_service import fuel_service, FuelService, OFFICIAL_CEYPETCO_TARIFFS, OFFICIAL_VEHICLE_EFFICIENCIES
from scripts.run_swagger import app

client = TestClient(app)


class TestFuelTariffDiscovery:
    """Verifies official Ceylon Petroleum Corporation data sources and tariffs."""

    def test_official_ceypetco_tariffs_present(self):
        prices = fuel_service.get_all_active_fuel_prices()
        assert len(prices) >= 5, "Should contain at least 5 active retail fuel types"

        fuel_types = {p["fuel_type"] for p in prices}
        expected_types = {
            "Petrol 92 Octane",
            "Petrol 95 Octane",
            "Auto Diesel",
            "Super Diesel",
            "Kerosene"
        }
        assert expected_types.issubset(fuel_types), f"Missing fuel types. Found: {fuel_types}"

    def test_official_retail_prices_and_provenance(self):
        p92 = fuel_service.get_fuel_price("Petrol 92 Octane")
        assert p92 is not None
        assert p92["price_per_litre_lkr"] == 414.00
        assert p92["source_url"] == "https://ceypetco.gov.lk/historical-prices/"
        assert "Ceylon Petroleum Corporation" in p92["source_notice"]
        assert isinstance(p92["effective_date"], (date, datetime))

        diesel = fuel_service.get_fuel_price("Auto Diesel")
        assert diesel is not None
        assert diesel["price_per_litre_lkr"] == 392.00
        assert diesel["is_active"] is True


class TestVehicleFuelEfficiencyCatalog:
    """Verifies normalized vehicle database models and provenance."""

    def test_catalog_population(self):
        vehicles = fuel_service.get_all_vehicle_efficiencies()
        assert len(vehicles) >= 14, "Should have seeded all popular Sri Lankan passenger vehicle models"

    def test_vehicle_specification_provenance(self):
        wagon_r = fuel_service.get_vehicle_by_id(1)
        assert wagon_r is not None
        assert wagon_r["make"] == "Suzuki"
        assert "Wagon R" in wagon_r["model"]
        assert wagon_r["consumption_unit"] == "km/L"
        assert wagon_r["published_consumption_value"] == 33.4
        assert wagon_r["test_cycle"] == "JC08"
        assert wagon_r["verification_status"] == "VERIFIED_MANUFACTURER_SPECIFICATION"
        assert "Suzuki Motor Corporation" in wagon_r["source_document"]

        prius = fuel_service.get_vehicle_by_id(2)
        assert prius is not None
        assert prius["make"] == "Toyota"
        assert "Prius" in prius["model"]
        assert prius["consumption_unit"] == "L/100 km"
        assert prius["published_consumption_value"] == 3.9
        assert prius["test_cycle"] == "WLTP"
        assert "Toyota Motor Corporation" in prius["source_document"]


class TestFuelCalculationsAndUnits:
    """Verifies mathematical formulas for both km/L and L/100 km units."""

    def test_calculation_with_km_per_litre_unit(self):
        # Formula: litres_used = distance_km / fuel_efficiency_km_per_litre
        # cost = litres_used * price_per_litre_lkr
        dist = 100.0
        eff = 33.4  # km/L (Wagon R)
        price = 414.0  # Petrol 92
        expected_litres = dist / eff  # 2.99401...
        expected_cost = expected_litres * price  # 1239.5209...

        res = fuel_service.estimate_fuel_cost(distance_km=dist, vehicle_id=1, is_return_trip=False)
        assert res["estimate_status"] == "VERIFIED"
        assert res["fuel_efficiency"]["unit"] == "km/L"
        assert res["litres_estimated"] == round(expected_litres, 2)
        assert res["total_fuel_cost_lkr"] == round(expected_cost, 2)
        assert res["is_laboratory_test_cycle"] is True
        assert "JC08" in res["fuel_efficiency"]["test_cycle"]

    def test_calculation_with_litres_per_100km_unit(self):
        # Formula: litres_used = distance_km * consumption_l_100km / 100
        # cost = litres_used * price_per_litre_lkr
        dist = 100.0
        consumption = 3.9  # L/100 km (Prius)
        price = 414.0  # Petrol 92
        expected_litres = dist * (consumption / 100.0)  # 3.9 litres
        expected_cost = expected_litres * price  # 1614.60 LKR

        res = fuel_service.estimate_fuel_cost(distance_km=dist, vehicle_id=2, is_return_trip=False)
        assert res["estimate_status"] == "VERIFIED"
        assert res["fuel_efficiency"]["unit"] == "L/100 km"
        assert res["litres_estimated"] == round(expected_litres, 2)
        assert res["total_fuel_cost_lkr"] == round(expected_cost, 2)
        assert res["is_laboratory_test_cycle"] is True
        assert "WLTP" in res["fuel_efficiency"]["test_cycle"]

    def test_unit_conversion_function(self):
        # 25 km/L -> 4.0 L/100 km
        l_100km = fuel_service.convert_fuel_efficiency(25.0, "km/L", "L/100 km")
        assert l_100km == 4.0

        # 4.0 L/100 km -> 25 km/L
        km_l = fuel_service.convert_fuel_efficiency(4.0, "L/100 km", "km/L")
        assert km_l == 25.0

        # Identity conversion
        assert fuel_service.convert_fuel_efficiency(18.0, "km/L", "km/L") == 18.0

        # Invalid conversion
        with pytest.raises(ValueError):
            fuel_service.convert_fuel_efficiency(0.0, "km/L", "L/100 km")


class TestJourneyTypesAndDistanceIntegrity:
    """Verifies one-way vs return trip calculations and avoidance of double-counting."""

    def test_one_way_trip(self):
        dist = 120.0
        res = fuel_service.estimate_fuel_cost(distance_km=dist, vehicle_id=1, is_return_trip=False)
        assert res["is_return_trip"] is False
        assert res["one_way_distance_km"] == 120.0
        assert res["total_trip_distance_km"] == 120.0

    def test_return_journey_doubles_distance_without_double_counting_one_way(self):
        one_way = 120.0
        res_one_way = fuel_service.estimate_fuel_cost(distance_km=one_way, vehicle_id=1, is_return_trip=False)
        res_return = fuel_service.estimate_fuel_cost(distance_km=one_way, vehicle_id=1, is_return_trip=True)

        assert res_return["is_return_trip"] is True
        assert res_return["one_way_distance_km"] == one_way
        assert res_return["total_trip_distance_km"] == one_way * 2.0
        assert pytest.approx(res_return["total_fuel_cost_lkr"], abs=0.05) == res_one_way["total_fuel_cost_lkr"] * 2.0


class TestUncertaintyAndFallbackHandling:
    """Verifies custom user average input, missing data, and uncertain cases."""

    def test_user_entered_average_efficiency(self):
        res = fuel_service.estimate_fuel_cost(
            distance_km=100.0,
            custom_efficiency_value=15.0,
            custom_efficiency_unit="km/L",
            fuel_type="Petrol 92 Octane"
        )
        assert res["estimate_status"] == "USER_ESTIMATE"
        assert res["litres_estimated"] == round(100.0 / 15.0, 2)
        assert res["total_fuel_cost_lkr"] == round((100.0 / 15.0) * 414.0, 2)
        assert res["fuel_efficiency"]["verification_status"] == "USER_ENTERED_AVERAGE"

    def test_incomplete_when_distance_is_zero_or_negative(self):
        res_zero = fuel_service.estimate_fuel_cost(distance_km=0.0, vehicle_id=1)
        assert res_zero["estimate_status"] == "INCOMPLETE"
        assert res_zero["total_fuel_cost_lkr"] is None

        res_neg = fuel_service.estimate_fuel_cost(distance_km=-50.0, vehicle_id=1)
        assert res_neg["estimate_status"] == "INCOMPLETE"

    def test_incomplete_when_efficiency_is_missing(self):
        res = fuel_service.estimate_fuel_cost(distance_km=100.0, vehicle_id=None, custom_efficiency_value=None)
        assert res["estimate_status"] == "INCOMPLETE"
        assert res["total_fuel_cost_lkr"] is None
        assert "Missing vehicle fuel efficiency" in res["completeness_reason"]

    def test_incomplete_when_fuel_type_is_unknown(self):
        res = fuel_service.estimate_fuel_cost(
            distance_km=100.0,
            custom_efficiency_value=15.0,
            fuel_type="Hydrogen Fuel Cell"
        )
        assert res["estimate_status"] == "INCOMPLETE"
        assert "not found" in res["completeness_reason"]

    def test_stale_fuel_price_warning(self):
        # Create a mock fuel service with a price notice older than 90 days
        stale_service = FuelService()
        stale_service._price_cache["Petrol 92 Octane"] = {
            "fuel_type": "Petrol 92 Octane",
            "price_per_litre_lkr": 371.00,
            "effective_date": date.today() - timedelta(days=120),
            "source_url": "https://ceypetco.gov.lk/historical-prices/",
            "source_notice": "Stale Ceypetco Notice",
            "is_active": True,
        }
        res = stale_service.estimate_fuel_cost(distance_km=100.0, vehicle_id=1)
        assert any("older than 90 days" in w for w in res["warnings"])


class TestFuelApiEndpoints:
    """Verifies REST API endpoints exposed by FastAPI."""

    def test_get_fuel_prices_endpoint(self):
        response = client.get("/api/fuel-prices")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "CEYPETCO" in data["data_source"]
        assert len(data["prices"]) >= 5

        first = data["prices"][0]
        assert "fuel_type" in first
        assert "price_per_litre_lkr" in first
        assert "effective_date" in first
        assert "source_url" in first

    def test_get_vehicles_fuel_efficiency_endpoint(self):
        response = client.get("/api/vehicles/fuel-efficiency")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] >= 14
        assert len(data["vehicles"]) >= 14

        first = data["vehicles"][0]
        assert "make" in first
        assert "model" in first
        assert "published_consumption_value" in first
        assert "consumption_unit" in first
        assert "test_cycle" in first

    def test_post_fuel_cost_estimate_endpoint(self):
        payload = {
            "distance_km": 115.5,
            "vehicle_id": 1,
            "is_return_trip": False
        }
        response = client.post("/api/fuel-cost/estimate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["estimate_status"] == "VERIFIED"
        assert data["one_way_distance_km"] == 115.5
        assert data["litres_estimated"] > 0
        assert data["total_fuel_cost_lkr"] > 0
        assert "disclaimer" in data

    def test_multimodal_plan_integration(self):
        # Test that multimodal plan response enriches car_option with fuel estimation
        # and cleanly separates ticket fares from car fuel cost in trip_cost_comparison
        payload = {
            "start": "Colombo",
            "end": "Kandy",
            "vehicle_id": 1,
            "fuel_type": "Petrol 92 Octane",
            "is_return_trip": False
        }
        response = client.post("/api/routes/multimodal-plan", json=payload)
        assert response.status_code == 200
        data = response.json()

        car_opt = data.get("car_option")
        assert car_opt is not None
        assert car_opt["available"] is True
        assert car_opt["ticket_fare_lkr"] == 0.0  # Public ticket fare is strictly 0.0
        assert car_opt["fuel_estimate_lkr"] is not None
        assert car_opt["fuel_cost_estimation"] is not None
        assert car_opt["fuel_grade"] == "Petrol 92 Octane"

        cost_comp = data.get("trip_cost_comparison")
        assert cost_comp is not None
        assert "public_transit_ticket_fare_lkr" in cost_comp
        assert "car_trip_fuel_cost_lkr" in cost_comp
        assert cost_comp["is_comparable"] is True
