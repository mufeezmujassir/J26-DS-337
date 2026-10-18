import pytest
import pandas as pd
from app.services.landslide_service import (
    LandslideService,
    LandslideRecord,
    haversine_distance_m,
    SRI_LANKA_BOUNDS,
)


def test_haversine_distance_accuracy():
    # Known distance: Colombo (6.9271, 79.8612) to Kandy (7.2906, 80.6337) ~ 95 km
    dist_m = haversine_distance_m(6.9271, 79.8612, 7.2906, 80.6337)
    assert 94000.0 < dist_m < 96000.0


def test_landslide_dataframe_validation_and_cleaning():
    # Synthetic DataFrame containing valid, invalid coords, NaN, and duplicate records
    raw_data = {
        "Case_ID": ["REC_VALID_1", "REC_VALID_2", "REC_NAN", "REC_OUT_BOUNDS", "REC_VALID_1"],
        "Inc_Type": ["Landslide", "Slope Failure", "Landslide", "Rock Fall", "Landslide"],
        "District": ["Badulla", "Kandy", "Kegalle", "Outland", "Badulla"],
        "DS_Name": ["Passara", "Yatinuwara", "Mawanella", "Unknown", "Passara"],
        "Date": ["2023-01-15", "2023-02-20", None, "2023-03-10", "2023-01-15"],
        "Latitude": [6.93, 7.25, None, 15.5, 6.93],      # 15.5 is outside Sri Lanka bounds
        "Longitude": [81.05, 80.55, 80.45, 95.0, 81.05], # 95.0 is outside Sri Lanka bounds
        "Rain_1h": [12.5, "25.0", None, 0.0, 12.5],
        "Rain_24h": [45.0, 80.0, None, 0.0, 45.0],
    }
    df = pd.DataFrame(raw_data)
    records = LandslideService._parse_and_validate_dataframe(df)

    # Should only keep 2 valid records (REC_VALID_1 deduplicated, REC_NAN dropped, REC_OUT_BOUNDS dropped)
    assert len(records) == 2
    rec1 = records[0]
    assert rec1.record_id == "REC_VALID_1"
    assert rec1.district == "Badulla"
    assert rec1.latitude == 6.93
    assert rec1.longitude == 81.05
    assert rec1.is_historical is True
    assert rec1.is_active_closure is False  # Must NOT be classified as active road closure
    assert rec1.rain_1h == 12.5
    assert rec1.rain_24h == 45.0


def test_landslide_historical_vs_active_closure_distinction():
    """Requirement 4: Historical landslide records are not automatically classified as confirmed current road closures."""
    record = LandslideRecord(
        record_id="TEST_HIST_01",
        incident_type="Landslide",
        district="Nuwara Eliya",
        ds_division="Walapane",
        event_date="2020-05-18",
        cause="Continuous rainfall",
        latitude=7.0,
        longitude=80.7,
    )
    assert record.is_historical is True
    assert record.is_active_closure is False

    d = record.to_dict()
    assert d["is_historical"] is True
    assert d["is_active_closure"] is False


def test_landslide_spatial_proximity_matching(tmp_path):
    # Create temporary CSV with known test hazards
    csv_file = tmp_path / "test_landslides.csv"
    csv_content = (
        "Case_ID,Inc_Type,District,DS_Name,Date,Latitude,Longitude,Rain_1h,Rain_24h\n"
        "HAZ_01,Landslide,Kandy,Kadugannawa,2022-06-10,7.2550,80.5250,15.0,60.0\n"
        "HAZ_02,Landslide,Badulla,Passara,2022-07-15,6.9500,81.1500,5.0,30.0\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    service = LandslideService(data_path=str(csv_file))
    assert len(service.records) == 2

    # Query route passing within 200m of HAZ_01 (7.2550, 80.5250)
    route_coords = [(7.2540, 80.5240), (7.2560, 80.5260)]
    hazards = service.find_hazards_near_route(route_coords, buffer_meters=1000.0)

    assert len(hazards) == 1
    matched = hazards[0]
    assert matched.record.record_id == "HAZ_01"
    assert matched.distance_meters < 500.0
    assert matched.proximity_zone == "CORRIDOR_DIRECT"
    assert "historical" in matched.advisory.lower()
    assert "road is not confirmed closed" in matched.advisory.lower()

    # Route far away from both (e.g. Jaffna, ~9.66, 80.02)
    jaffna_coords = [(9.66, 80.02), (9.67, 80.03)]
    jaffna_hazards = service.find_hazards_near_route(jaffna_coords, buffer_meters=1000.0)
    assert len(jaffna_hazards) == 0

    # Route summary for safe route
    summary_safe = service.assess_route_summary(jaffna_coords, buffer_meters=1000.0)
    assert summary_safe["status"] == "NO_RISK_DETECTED"
    assert summary_safe["hazard_count"] == 0

    # Route summary for hazardous route
    summary_haz = service.assess_route_summary(route_coords, buffer_meters=1000.0)
    assert summary_haz["status"] == "RISK_DETECTED"
    assert summary_haz["hazard_count"] == 1
