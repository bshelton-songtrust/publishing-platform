"""Tests for health check endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test basic health check endpoint."""
    response = await client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "status" in data
    assert "timestamp" in data
    assert "version" in data
    assert "environment" in data
    assert "dependencies" in data
    
    # Check that we have some dependency checks
    assert isinstance(data["dependencies"], dict)


@pytest.mark.asyncio 
async def test_version_endpoint(client: AsyncClient):
    """Test version information endpoint."""
    response = await client.get("/version")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "service" in data
    assert "version" in data
    assert "environment" in data
    assert "api_version" in data
    assert data["service"] == "catalog-management-service"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint."""
    response = await client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "service" in data
    assert "version" in data
    assert "status" in data
    assert data["status"] == "running"