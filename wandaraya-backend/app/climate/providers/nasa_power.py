"""NASA POWER Daily point adapter.  No database behaviour lives here."""
from __future__ import annotations
import hashlib, json, time
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT="https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS=("T2M","T2M_MAX","T2M_MIN","PRECTOTCORR","RH2M","WS10M","ALLSKY_SFC_SW_DWN")
INTERNAL={"T2M":"temperature_mean_c","T2M_MAX":"temperature_max_c","T2M_MIN":"temperature_min_c","PRECTOTCORR":"precipitation_mm","RH2M":"relative_humidity_pct","WS10M":"wind_speed_10m","ALLSKY_SFC_SW_DWN":"solar_radiation"}

class NasaPowerError(RuntimeError): pass
@dataclass(frozen=True)
class NasaPowerRequest:
    latitude: float; longitude: float; start: date; end: date; time_standard: str="UTC"
    def __post_init__(self):
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180: raise ValueError("invalid coordinates")
        if self.start > self.end: raise ValueError("start must not follow end")
        if self.time_standard not in {"UTC","LST"}: raise ValueError("time_standard must be UTC or LST")
    def url(self):
        return ENDPOINT+"?"+urlencode({"community":"AG","latitude":self.latitude,"longitude":self.longitude,"start":self.start.strftime("%Y%m%d"),"end":self.end.strftime("%Y%m%d"),"parameters":",".join(PARAMETERS),"format":"JSON","time-standard":self.time_standard})

def fetch(request: NasaPowerRequest, timeout: int=30, retries: int=2) -> tuple[dict, bytes]:
    error=None
    for attempt in range(retries+1):
        try:
            http=Request(request.url(),headers={"User-Agent":"WANDARAYA-Research/Stage12.4B1"})
            with urlopen(http,timeout=timeout) as response:
                raw=response.read()
                if response.status != 200: raise NasaPowerError(f"http_{response.status}")
            payload=json.loads(raw)
            if "messages" in payload and payload["messages"]: raise NasaPowerError("provider_messages:"+str(payload["messages"]))
            if "properties" not in payload or "parameter" not in payload["properties"]: raise NasaPowerError("malformed_response")
            return payload, raw
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, NasaPowerError) as exc:
            error=exc
            if attempt < retries: time.sleep(2**attempt)
    raise NasaPowerError(str(error))

def normalize(payload: dict) -> tuple[list[dict], dict]:
    properties=payload["properties"]; parameters=properties["parameter"]; header=payload.get("header",{}); fill=header.get("fill_value", -999)
    dates=sorted(set().union(*(values.keys() for values in parameters.values())))
    records=[]
    for day in dates:
        row={"date":f"{day[:4]}-{day[4:6]}-{day[6:8]}"}
        for source, internal in INTERNAL.items():
            value=parameters.get(source,{}).get(day)
            row[internal]=None if value in (fill,-999,-999.0) else value
        records.append(row)
    # POWER places declared parameter units at the response top level, not in
    # properties.parameter (which contains date/value series).
    units={key: value.get("units") for key,value in payload.get("parameters",{}).items()} if isinstance(payload.get("parameters"),dict) else {}
    return records,{"header":header,"units":units,"source_parameters":list(parameters),"response_checksum_sha256":hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()}
