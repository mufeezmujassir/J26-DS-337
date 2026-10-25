"""
WANDARAYA Component 2: Fuel Prices & Vehicle Fuel-Cost Estimation Router
========================================================================
Endpoints:
- GET  /api/fuel-prices
- GET  /api/vehicles/fuel-efficiency
- POST /api/fuel-cost/estimate
"""

import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query, status

from app.services.fuel_service import fuel_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Fuel & Car Travel Cost Estimation"])


class FuelEstimateRequest(BaseModel):
    distance_km: float = Field(..., description="Actual driving route distance in kilometers (must be > 0)")
    vehicle_id: Optional[int] = Field(None, description="Optional ID of verified vehicle specification")
    fuel_type: Optional[str] = Field(None, description="Fuel grade, e.g., 'Petrol 92 Octane', 'Petrol 95 Octane', 'Auto Diesel', 'Super Diesel'")
    custom_efficiency_value: Optional[float] = Field(None, description="User-entered fuel efficiency when verified specification is unavailable or user overrides")
    custom_efficiency_unit: Optional[str] = Field("km/L", description="Efficiency unit: 'km/L' or 'L/100 km'")
    is_return_trip: bool = Field(False, description="Whether this is a two-way return journey (doubles trip distance without double-counting one-way distance)")


@router.get("/api/fuel-prices")
@router.get("/fuel-prices", include_in_schema=False)
async def get_official_fuel_prices() -> Dict[str, Any]:
    """
    Retrieves all verified official Ceylon Petroleum Corporation (CEYPETCO) retail fuel tariffs.
    Source: https://ceypetco.gov.lk/historical-prices/
    """
    prices = fuel_service.get_all_active_fuel_prices()
    return {
        "status": "success",
        "data_source": "Ceylon Petroleum Corporation (CEYPETCO)",
        "source_url": "https://ceypetco.gov.lk/historical-prices/",
        "prices": prices,
    }


@router.get("/api/vehicles/fuel-efficiency")
@router.get("/vehicles/fuel-efficiency", include_in_schema=False)
async def get_vehicle_fuel_efficiencies(
    make: Optional[str] = Query(None, description="Filter by vehicle make, e.g., 'Toyota', 'Suzuki', 'Honda'"),
    fuel_type: Optional[str] = Query(None, description="Filter by fuel type, e.g., 'Petrol 92 Octane', 'Auto Diesel'")
) -> Dict[str, Any]:
    """
    Retrieves normalized vehicle fuel efficiency database entries with manufacturer specifications,
    test-cycle standards (WLTP, JC08, NEDC, ARAI), source documents, and verification provenance.
    """
    vehicles = fuel_service.get_all_vehicle_efficiencies(make=make, fuel_type=fuel_type)
    return {
        "status": "success",
        "count": len(vehicles),
        "vehicles": vehicles,
    }


@router.post("/api/fuel-cost/estimate")
@router.post("/fuel-cost/estimate", include_in_schema=False)
async def estimate_fuel_cost(payload: FuelEstimateRequest) -> Dict[str, Any]:
    """
    Estimates vehicle fuel consumption and trip fuel cost in LKR based on actual route distance,
    selected vehicle efficiency or user-entered efficiency, and official Ceypetco retail fuel prices.
    Supports both km/L and L/100 km units, one-way and return journeys, and uncertainty metadata.
    """
    result = fuel_service.estimate_fuel_cost(
        distance_km=payload.distance_km,
        vehicle_id=payload.vehicle_id,
        fuel_type=payload.fuel_type,
        custom_efficiency_value=payload.custom_efficiency_value,
        custom_efficiency_unit=payload.custom_efficiency_unit,
        is_return_trip=payload.is_return_trip,
    )
    return result
