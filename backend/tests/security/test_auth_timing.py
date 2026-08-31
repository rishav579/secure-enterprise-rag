import time
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_auth_timing_oracle_mitigation(client: AsyncClient):
    # Register a user first to have a valid email in DB
    await client.post("/api/v1/auth/register", json={"email": "timing@example.com", "password": "StrongPassword123!"})

    # Test valid user with wrong password
    start_valid = time.perf_counter()
    await client.post("/api/v1/auth/login", json={"email": "timing@example.com", "password": "wrongpassword"})
    time_valid = time.perf_counter() - start_valid

    # Test invalid user
    start_invalid = time.perf_counter()
    await client.post("/api/v1/auth/login", json={"email": "nonexistent@example.com", "password": "wrongpassword"})
    time_invalid = time.perf_counter() - start_invalid

    # The times should be relatively close.
    ratio = time_valid / time_invalid if time_invalid > 0 else 0
    assert 0.2 < ratio < 5.0, f"Timing vulnerability detected: Valid={time_valid:.4f}s, Invalid={time_invalid:.4f}s"
