from __future__ import annotations

import httpx
import pytest

from app.knowledge_base.connectors.mediawiki import MediaWikiApiClient
from app.knowledge_base.connectors.wikipedia import WikipediaConnector
from app.knowledge_base.connectors.wikivoyage import WikivoyageConnector


def mock_factory(responses: list[httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        response = responses.pop(0)
        return httpx.Response(response.status_code, headers=response.headers, json=response.json(), request=request)
    transport = httpx.MockTransport(handler)
    return lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs)


@pytest.mark.asyncio
async def test_mediawiki_client_retries_429_using_retry_after_zero_without_fabricating_content():
    client = MediaWikiApiClient("https://example.invalid/w/api.php", min_request_interval_seconds=0,
        client_factory=mock_factory([httpx.Response(429, headers={"Retry-After": "0"}, json={}), httpx.Response(200, json={"query": {}})]))
    assert await client.get_json({"action": "query"}) == {"query": {}}


@pytest.mark.asyncio
async def test_wikipedia_connector_uses_shared_politeness_client(monkeypatch):
    connector = WikipediaConnector()
    async def get_json(params):
        assert params["list"] == "search"
        return {"query": {"search": [{"title": "Galle Fort"}]}}
    monkeypatch.setattr(connector.client, "get_json", get_json)
    assert await connector.search("Galle Fort") == [{"title": "Galle Fort"}]


@pytest.mark.asyncio
async def test_wikivoyage_connector_returns_none_for_missing_page(monkeypatch):
    connector = WikivoyageConnector()
    async def get_json(params):
        return {"query": {"pages": [{"missing": True}]}}
    monkeypatch.setattr(connector.client, "get_json", get_json)
    assert await connector.get_page_extract("Missing") is None
