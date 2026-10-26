from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from backend.app.config import Settings
from backend.app.main import create_app


async def test_health_endpoint(test_settings: Settings) -> None:
    app = create_app(test_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "autoagent"
