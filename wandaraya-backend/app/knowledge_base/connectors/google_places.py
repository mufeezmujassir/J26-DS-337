"""
Google Places Connector

Responsibilities:
- Connect to the Google Places API.
- Search for places around a geometry location.
retriew the detailed information for the specefic places
return raw API response data for further processing.


"""


from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

GOOGLE_PLACE_API_KEY=os.getenv("GOOGLE_PLACES_API_KEY")
GOOGLE_PLACE_BASE_URL=os.getenv(
    "GOOGLE_PLACES_BASE_URL",
    "https://places.googleapis.com/v1",
)

if not GOOGLE_PLACE_API_KEY:
    raise RuntimeError("GOOGLE_PLACES_API_KEY environment variable is not set.")


class GooglePlacesConnector:
    def __init__(self, api_key: str = GOOGLE_PLACE_API_KEY,base_url: str = GOOGLE_PLACE_BASE_URL,timeout: float = 10) -> None:

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _build_headers(self,fieldmask:str,)->Dict[str,str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": fieldmask,
        }
    async def nearby_search(
            self,
            latitude:float,
            longitude:float,
            radius:float=5000.0,
            included_types:Optional[List[str]]=None,
            max_results:int=20,
    )->List[Dict[str,Any]]:

        url=f"{self.base_url}/places:searchNearby"

        payload:Dict[str,Any]={
            "maxResultCount":max_results,
            "locationRestriction":{
                "circle":{
                    "center":{
                        "latitude":latitude,
                        "longitude":longitude,
                    },
                    "radius":radius,
                }
            }
            
        }
        if included_types:
            payload["includedTypes"] = included_types


        field_mask = ",".join(
            [
                "places.id",
                "places.displayName",
                "places.formattedAddress",
                "places.location",
                "places.primaryType",
                "places.types",
            ]
        )
        headers=self._build_headers(field_mask)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data=response.json()
            return data.get("places",[])

    async def get_place_details(
            self, place_id:str)->Dict[str,Any]:
        url=f"{self.base_url}/places/{place_id}"
        field_mask = ",".join(
             [
                 "id",
                "displayName",
                "formattedAddress",
                "addressComponents",
                "location",
                "primaryType",
                "types",
                "rating",
                "userRatingCount",
                "websiteUri",
                "internationalPhoneNumber",
                "regularOpeningHours",
                "priceLevel",
                "businessStatus",
                "googleMapsUri",
                "photos",
             ]
        )

        headers=self._build_headers(field_mask)

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data=response.json()
            return data

    async def get_photo_metadata(
            self,
            photo_name,
            max_width:int=1200,
            max_height:int=1200,

    )->Dict[str,Any]:

        if not photo_name:
            raise ValueError("photo_name is required")
        url=(
            f"{self.base_url}/"f"{photo_name}/media"
        )

        params={
            "key": self.api_key,
        "maxWidthPx": max_width,
        "maxHeightPx": max_height,

        # Return metadata containing photoUri
        # rather than immediately following
        # the image redirect.
        "skipHttpRedirect": "true",
        
        }

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data=response.json()
            return data


