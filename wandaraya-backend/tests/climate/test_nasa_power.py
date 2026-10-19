from datetime import date
from app.climate.providers.nasa_power import NasaPowerRequest, normalize

def test_request_is_explicit_and_bounded():
    url=NasaPowerRequest(6.03,80.21,date(2024,1,1),date(2024,12,31)).url()
    assert "time-standard=UTC" in url and "PRECTOTCORR" in url

def test_normalize_converts_sentinel_to_none():
    payload={"header":{"fill_value":-999},"properties":{"parameter":{"T2M":{"20240101":28},"T2M_MAX":{"20240101":30},"T2M_MIN":{"20240101":26},"PRECTOTCORR":{"20240101":-999},"RH2M":{"20240101":70},"WS10M":{"20240101":2},"ALLSKY_SFC_SW_DWN":{"20240101":10}}}}
    rows,_=normalize(payload)
    assert rows[0]["precipitation_mm"] is None and rows[0]["temperature_mean_c"]==28
