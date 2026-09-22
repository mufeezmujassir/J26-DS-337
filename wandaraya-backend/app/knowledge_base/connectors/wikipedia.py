from __future__ import annotations
from typing import Any, Dict, List, Optional
import httpx

class WikipediaConnector:
    BASE_URL="https://en.wikipedia.org/w/api.php"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "WANDARAYA-Tourism-Research/1.0 "
                "( Research Project)"
            )
        }

    async def search(self, query: str,limit: int=5) -> List[Dict[str, Any]]:
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
            "utf8": 1,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers
        )as client:
            response=await client.get(self.BASE_URL,params=params)
            response.raise_for_status()
            data=response.json()
        return(
            data.get("query", {}).get("search", [])
        )

    async def get_page_extract(
            self,
            title:str,

    )->Optional[Dict[str,Any]]:
        params = {
            "action": "query",
            "prop": "extracts|info",
            "titles": title,

            # Plain text instead of HTML
            "explaintext": 1,

            # Full article extract
            "exintro": 0,

            "inprop": "url",
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
        ) as client:

            response = await client.get(
                self.BASE_URL,
                params=params,
            )

            response.raise_for_status()

            data = response.json()

        pages = (
            data
            .get("query", {})
            .get("pages", [])
        )

        if not pages:
            return None

        page = pages[0]

        if page.get("missing"):
            return None

        return {
            "page_id": page.get("pageid"),
            "title": page.get("title"),
            "description": page.get("extract"),
            "source_url": page.get("fullurl"),
            "language": "en",
        }
