"""Smoke tests for the application foundation."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.main import app


@pytest.mark.asyncio
async def test_application_starts_and_exposes_openapi(test_client) -> None:
    response = await test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "GigBridge API"
    assert {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/workspaces",
        "/api/v1/workspaces/{workspace_id}",
    }.issubset(schema["paths"])


@pytest.mark.asyncio
async def test_live_health(test_client) -> None:
    response = await test_client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_health_when_database_is_available(test_client) -> None:
    with patch("app.main.check_database_ready", new_callable=AsyncMock):
        response = await test_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.asyncio
async def test_ready_health_when_database_is_unavailable(test_client) -> None:
    with patch(
        "app.main.check_database_ready",
        new_callable=AsyncMock,
        side_effect=SQLAlchemyError("database unavailable"),
    ):
        response = await test_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_versioned_api_router_is_mounted() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/v1" in paths or any(path.startswith("/api/v1") for path in paths)


@pytest.mark.asyncio
async def test_request_id_is_generated_and_echoed(test_client) -> None:
    response = await test_client.get("/health/live")
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_valid_request_id_is_preserved(test_client) -> None:
    request_id = "test-request-123"
    response = await test_client.get("/health/live", headers={"X-Request-ID": request_id})
    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.asyncio
async def test_error_response_format(test_client) -> None:
    response = await test_client.get("/missing-route")
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message", "request_id"}
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
