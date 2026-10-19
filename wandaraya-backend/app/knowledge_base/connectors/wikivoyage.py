from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.knowledge_base.connectors.mediawiki import MediaWikiApiClient


class WikivoyageConnector:

    BASE_URL = (
        "https://en.wikivoyage.org/w/api.php"
    )

    def __init__(self) -> None:

        self.client = MediaWikiApiClient(self.BASE_URL)

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:

        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
            "utf8": 1,
        }

        data = await self.client.get_json(params)

        return (
            data
            .get("query", {})
            .get("search", [])
        )

    async def get_page_extract(
        self,
        title: str,
    ) -> Optional[Dict[str, Any]]:

        params = {
            "action": "query",
            "prop": "extracts|info",
            "titles": title,
            "explaintext": 1,
            "inprop": "url",
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }

        data = await self.client.get_json(params)

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
