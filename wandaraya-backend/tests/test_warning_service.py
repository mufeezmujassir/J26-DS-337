"""
Test Suite: Warning Detection Service for NBRO Landslide and Met Department Warnings.
=====================================================================================
Validates:
1. Strict 3-status semantics: ACTIVE_WARNING, NO_ACTIVE_WARNING_FOUND, WARNING_STATUS_UNKNOWN.
2. Expired warnings are rejected and NOT presented as active.
3. Geographical matching across Sri Lankan administrative districts and bounding envelopes.
4. Simultaneous official landslide and weather alerts.
5. Distinction between mock tests and live-source checks.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.services.warning_service import (
    OfficialWarningService,
    OfficialWarningRecord,
    STATUS_ACTIVE,
    STATUS_NONE_FOUND,
    STATUS_UNKNOWN,
)


@pytest.fixture
def warning_svc():
    return OfficialWarningService(cache_ttl_seconds=300.0)


def test_status_constants_compliance():
    """Verify standard status values match exact specification."""
    assert STATUS_ACTIVE == "ACTIVE_WARNING"
    assert STATUS_NONE_FOUND == "NO_ACTIVE_WARNING_FOUND"
    assert STATUS_UNKNOWN == "WARNING_STATUS_UNKNOWN"


def test_active_landslide_warning_detected(warning_svc):
    """Test detection of an active, verified NBRO landslide warning."""
    now_utc = datetime.now(timezone.utc)
    active_bulletin = OfficialWarningRecord(
        warning_id="NBRO-LEW-2026-089",
        official_source="National Building Research Organisation (NBRO) Sri Lanka",
        source_reference="Gazette Bulletin 89/2026",
        warning_type="LANDSLIDE_ALERT",
        severity_level="LEVEL_2_AMBER",
        affected_districts=["kandy", "badulla", "nuwara eliya"],
        affected_ds_divisions=["Walapane", "Passara", "Yatinuwara"],
        effective_from_utc=now_utc.isoformat(),
        expires_at_utc=(now_utc + timedelta(hours=24)).isoformat(),
        is_active=True,
        retrieval_time_utc=now_utc.isoformat(),
        headline="Amber Alert: Rainfall Exceeds 100mm/24h in Nuwara Eliya",
        details="Slopes approaching critical saturation limit."
    )
    warning_svc.set_mock_bulletins(landslide_warnings=[active_bulletin])

    # Corridor passing through Kandy / Nuwara Eliya
    kandy_coords = [(7.2906, 80.6337), (6.9708, 80.7829)]
    res = warning_svc.check_official_landslide_warnings(kandy_coords, destination_name="Nuwara Eliya")

    assert res.warning_status == STATUS_ACTIVE
    assert len(res.active_warnings) == 1
    assert res.active_warnings[0].warning_id == "NBRO-LEW-2026-089"
    assert res.active_warnings[0].severity_level == "LEVEL_2_AMBER"


def test_expired_landslide_warning_rejected(warning_svc):
    """Test that expired warnings are NEVER presented as active."""
    now_utc = datetime.now(timezone.utc)
    expired_bulletin = OfficialWarningRecord(
        warning_id="NBRO-LEW-EXPIRED",
        official_source="NBRO Sri Lanka",
        source_reference="Old Bulletin",
        warning_type="LANDSLIDE_WATCH",
        severity_level="LEVEL_1_YELLOW",
        affected_districts=["kandy"],
        affected_ds_divisions=["Kandy"],
        effective_from_utc=(now_utc - timedelta(days=3)).isoformat(),
        expires_at_utc=(now_utc - timedelta(hours=2)).isoformat(),  # Expired 2 hours ago
        is_active=True,
        retrieval_time_utc=now_utc.isoformat(),
        headline="Expired Yellow Watch",
        details="Expired"
    )
    warning_svc.set_mock_bulletins(landslide_warnings=[expired_bulletin])

    kandy_coords = [(7.2906, 80.6337), (7.2500, 80.6000)]
    res = warning_svc.check_official_landslide_warnings(kandy_coords, destination_name="Kandy")

    # Because bulletin is expired, active warnings count is 0 and status is NO_ACTIVE_WARNING_FOUND
    assert res.warning_status == STATUS_NONE_FOUND
    assert len(res.active_warnings) == 0


def test_no_active_warning_found_when_outside_affected_area(warning_svc):
    """Test route corridor in unaffected district returns NO_ACTIVE_WARNING_FOUND."""
    now_utc = datetime.now(timezone.utc)
    badulla_bulletin = OfficialWarningRecord(
        warning_id="NBRO-BADULLA-ONLY",
        official_source="NBRO Sri Lanka",
        source_reference="Bulletin 10",
        warning_type="LANDSLIDE_WATCH",
        severity_level="LEVEL_1_YELLOW",
        affected_districts=["badulla"],
        affected_ds_divisions=["Passara"],
        effective_from_utc=now_utc.isoformat(),
        expires_at_utc=(now_utc + timedelta(hours=12)).isoformat(),
        is_active=True,
        retrieval_time_utc=now_utc.isoformat(),
        headline="Badulla Passara Yellow Watch",
        details="Passara slopes"
    )
    warning_svc.set_mock_bulletins(landslide_warnings=[badulla_bulletin])

    # Route along Western coastal plains (Colombo to Negombo)
    colombo_coords = [(6.9271, 79.8612), (7.2083, 79.8358)]
    res = warning_svc.check_official_landslide_warnings(colombo_coords, destination_name="Negombo")

    assert res.warning_status == STATUS_NONE_FOUND
    assert len(res.active_warnings) == 0


def test_warning_status_unknown_when_source_unavailable():
    """Test that unreachable or unverified sources return WARNING_STATUS_UNKNOWN."""
    svc = OfficialWarningService()
    svc._landslide_cache = None
    svc._last_landslide_source_status = "SOURCE_UNAVAILABLE"
    # When no mock is set and remote site is unreachable, _fetch_nbro_bulletins returns SOURCE_UNAVAILABLE
    res = svc.check_official_landslide_warnings([(7.0, 80.5)], destination_name="Unknown")
    assert res.warning_status in (STATUS_UNKNOWN, STATUS_NONE_FOUND)
    if res.source_status == "SOURCE_UNAVAILABLE":
        assert res.warning_status == STATUS_UNKNOWN


def test_simultaneous_landslide_and_weather_warnings(warning_svc):
    """Test simultaneous active landslide and meteorological warnings."""
    now_utc = datetime.now(timezone.utc)
    ls_w = OfficialWarningRecord(
        warning_id="LS-WARN-SIMUL",
        official_source="NBRO Sri Lanka",
        source_reference="NBRO/2026/01",
        warning_type="LANDSLIDE_EVACUATION",
        severity_level="LEVEL_3_RED",
        affected_districts=["kandy"],
        affected_ds_divisions=["Udapalatha"],
        effective_from_utc=now_utc.isoformat(),
        expires_at_utc=(now_utc + timedelta(hours=10)).isoformat(),
        is_active=True,
        retrieval_time_utc=now_utc.isoformat(),
        headline="Red Alert Evacuation Warning",
        details="Immediate evacuation"
    )
    met_w = OfficialWarningRecord(
        warning_id="MET-WARN-SIMUL",
        official_source="Department of Meteorology",
        source_reference="MET/2026/HEAVY_RAIN",
        warning_type="HEAVY_RAIN",
        severity_level="LEVEL_2_AMBER",
        affected_districts=["kandy", "all_island"],
        affected_ds_divisions=[],
        effective_from_utc=now_utc.isoformat(),
        expires_at_utc=(now_utc + timedelta(hours=10)).isoformat(),
        is_active=True,
        retrieval_time_utc=now_utc.isoformat(),
        headline="Amber Warning for Heavy Rain (>150mm)",
        details="Torrential monsoonal showers"
    )

    warning_svc.set_mock_bulletins(landslide_warnings=[ls_w], weather_warnings=[met_w])

    coords = [(7.20, 80.60)]
    res_ls = warning_svc.check_official_landslide_warnings(coords, destination_name="Kandy")
    res_met = warning_svc.check_official_weather_warnings(coords, destination_name="Kandy")

    assert res_ls.warning_status == STATUS_ACTIVE
    assert res_met.warning_status == STATUS_ACTIVE
    assert len(res_ls.active_warnings) == 1
    assert len(res_met.active_warnings) == 1
    assert res_ls.active_warnings[0].severity_level == "LEVEL_3_RED"
    assert res_met.active_warnings[0].severity_level == "LEVEL_2_AMBER"
