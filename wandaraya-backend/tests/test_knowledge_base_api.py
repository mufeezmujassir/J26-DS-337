from fastapi.testclient import TestClient

from app.main import app


def test_knowledge_base_endpoints_are_published_in_swagger_openapi() -> None:
    document = TestClient(app).get("/openapi.json").json()
    assert "/api/v1/knowledge-base/status" in document["paths"]
    assert "/api/v1/knowledge-base/attractions" in document["paths"]
    assert "/api/v1/knowledge-base/attractions/{attraction_id}" in document["paths"]
    assert "/api/v1/knowledge-base/semantic-search" in document["paths"]
    assert "/api/v1/knowledge-base/attractions/nearby" in document["paths"]
    assert "/api/v1/knowledge-base/categories" in document["paths"]
    assert "/api/v1/knowledge-base/districts" in document["paths"]
    assert "/api/v1/knowledge-base/sources" in document["paths"]
    assert "/api/v1/knowledge-base/quality" in document["paths"]
