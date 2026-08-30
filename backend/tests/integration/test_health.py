import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock
from backend.app.api.deps import get_db
from backend.app.main import create_app


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint returns application metadata."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Secure Enterprise RAG"
    assert data["status"] == "online"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_check_success(client: AsyncClient):
    """Test health check returns 200 when database is healthy."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "healthy"
    assert data["environment"] == "testing"


@pytest.mark.asyncio
async def test_health_check_database_failure():
    """Test health check returns 503 when database execution fails."""
    app = create_app()

    # Mock DB session that raises an error on execute
    mock_db = AsyncMock()
    mock_db.execute.side_effect = ConnectionError("Database connection lost")

    async def _failing_db():
        yield mock_db

    app.dependency_overrides[get_db] = _failing_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "degraded"
        assert "ConnectionError" in data["detail"]["database"]
