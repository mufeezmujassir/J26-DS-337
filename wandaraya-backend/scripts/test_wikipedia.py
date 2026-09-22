from __future__ import annotations
from typing import Any, Dict, List, Optional
import asyncio

from app.knowledge_base.connectors.wikipedia import WikipediaConnector
from app.knowledge_base.connectors.wikivoyage import WikivoyageConnector
async def main():

    #connector=WikipediaConnector()
    connector=WikivoyageConnector()
    query="Galle Dutch Fort Sri Lanka"
    print("\n==============================")
    print("WIKIPEDIA SEARCH")
    print("==============================")
    results = await connector.search(query=query, limit=5)
    for index, result in enumerate(
        results,
        start=1,
    ):

        print(
            f"{index}. "
            f"{result.get('title')}"
        )

    if not results:
        return

    title = results[0]["title"]

    print("\nSelected:")
    print(title)

    page = await connector.get_page_extract(
        title
    )

    print("\n==============================")
    print("WIKIPEDIA CONTENT")
    print("==============================")

    if not page:

        print("Page not found.")
        return

    print(f"Page ID: {page['page_id']}")
    print(f"Title: {page['title']}")
    print(f"URL: {page['source_url']}")

    description = (
        page["description"] or ""
    )

    print("\nDescription Preview:")
    print(description[:1500])


if __name__ == "__main__":
    asyncio.run(main())