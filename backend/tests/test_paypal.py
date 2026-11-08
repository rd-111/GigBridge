"""PayPal adapter and ledger API tests without live provider credentials."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.integrations.paypal.auth import PayPalOAuth
from app.integrations.paypal.client import PayPalAPIClient
from app.integrations.paypal.exceptions import (
    PayPalAuthenticationError,
    PayPalConfigurationError,
    PayPalInvalidResponseError,
    PayPalRateLimitError,
    PayPalTimeoutError,
    PayPalUnavailableError,
)
from app.models import LedgerEntry


def settings(**values) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        jwt_secret_key="test-only-signing-secret-with-at-least-32-characters",
        **values,
    )


@pytest.mark.asyncio
async def test_oauth_caches_token_and_refreshes_when_forced():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"access_token": f"token-{calls}", "expires_in": 3600, "scope": "https://uri.paypal.com/services/reporting/search/read"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://sandbox.test") as http:
        oauth = PayPalOAuth(http, settings(paypal_client_id="id", paypal_client_secret="secret"))
        assert (await oauth.get_token()).access_token == "token-1"
        assert (await oauth.get_token()).access_token == "token-1"
        assert (await oauth.get_token(force_refresh=True)).access_token == "token-2"
    assert calls == 2


@pytest.mark.asyncio
async def test_oauth_missing_credentials_invalid_credentials_and_timeout():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401)), base_url="https://sandbox.test") as http:
        with pytest.raises(PayPalConfigurationError):
            await PayPalOAuth(http, settings()).get_token()
        oauth = PayPalOAuth(http, settings(paypal_client_id="id", paypal_client_secret="secret"))
        with pytest.raises(PayPalAuthenticationError):
            await oauth.get_token()

    async def timeout_handler(_request):
        raise httpx.TimeoutException("private details")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler), base_url="https://sandbox.test") as http:
        oauth = PayPalOAuth(http, settings(paypal_client_id="id", paypal_client_secret="secret"))
        with pytest.raises(PayPalTimeoutError):
            await oauth.get_token()


@pytest.mark.asyncio
async def test_transaction_client_handles_pages_empty_rows_and_rate_limit():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600, "scope": "https://uri.paypal.com/services/reporting/search/read"})
        page = int(request.url.params["page"])
        calls.append(page)
        if request.headers.get("x-rate-test"):
            return httpx.Response(429)
        if page == 1:
            return httpx.Response(200, json={"total_pages": 2, "transaction_details": [{"transaction_info": {"transaction_id": "tx-1", "transaction_event_code": "T0006", "transaction_amount": {"value": "12.34", "currency_code": "USD"}, "transaction_initiation_date": "2026-01-01T00:00:00Z", "transaction_status": "S"}}]})
        return httpx.Response(200, json={"total_pages": 2, "transaction_details": []})

    client = PayPalAPIClient(settings(paypal_client_id="id", paypal_client_secret="secret"), transport=httpx.MockTransport(handler))
    rows = await client.transactions(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC))
    assert len(rows) == 1 and rows[0].amount == Decimal("12.34") and rows[0].direction == "income"
    assert calls == [1, 2]
    await client.close()

    def empty_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600, "scope": "https://uri.paypal.com/services/reporting/search/read"})
        return httpx.Response(200, json={"total_pages": 1, "transaction_details": []})

    client = PayPalAPIClient(settings(paypal_client_id="id", paypal_client_secret="secret"), transport=httpx.MockTransport(empty_handler))
    assert await client.transactions(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)) == []
    await client.close()

    def rate_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600, "scope": "https://uri.paypal.com/services/reporting/search/read"})
        return httpx.Response(429)

    client = PayPalAPIClient(settings(paypal_client_id="id", paypal_client_secret="secret"), transport=httpx.MockTransport(rate_handler))
    with pytest.raises(PayPalRateLimitError):
        await client.transactions(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC))
    await client.close()

    for response, expected_error in [
        (httpx.Response(503), PayPalUnavailableError),
        (httpx.Response(200, json={"transaction_details": "not-a-list"}), PayPalInvalidResponseError),
    ]:
        def error_handler(request: httpx.Request, response=response) -> httpx.Response:
            if request.url.path.endswith("/oauth2/token"):
                return httpx.Response(200, json={"access_token": "token", "expires_in": 3600, "scope": "https://uri.paypal.com/services/reporting/search/read"})
            return response

        client = PayPalAPIClient(settings(paypal_client_id="id", paypal_client_secret="secret"), transport=httpx.MockTransport(error_handler))
        with pytest.raises(expected_error):
            await client.transactions(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC))
        await client.close()


@pytest.mark.asyncio
async def test_demo_sync_ledger_listing_summary_and_workspace_isolation(test_client, monkeypatch):
    # Register user through Phase 2 API and use its JWT for genuine authorization.
    registration = await test_client.post("/api/v1/auth/register", json={"email": "demo@example.com", "password": "StrongPassword123!", "full_name": "Demo", "workspace_name": "Demo"})
    assert registration.status_code == 201
    login = await test_client.post("/api/v1/auth/login", json={"email": "demo@example.com", "password": "StrongPassword123!"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = registration.json()["workspace"]["id"]

    test_settings = settings(paypal_mode="demo")
    test_client._transport.app.dependency_overrides[get_settings] = lambda: test_settings
    status = await test_client.get(f"/api/v1/paypal/status?workspace_id={workspace_id}", headers=headers)
    assert status.status_code == 200 and status.json()["connection_status"] == "disconnected"
    capabilities = await test_client.post(f"/api/v1/paypal/permission-check?workspace_id={workspace_id}", headers=headers)
    assert capabilities.status_code == 200 and capabilities.json()["demo_mode"] is True
    sync = await test_client.post("/api/v1/paypal/sync", headers=headers, json={"workspace_id": workspace_id, "start_date": "2026-01-01T00:00:00Z", "end_date": "2026-01-31T00:00:00Z"})
    assert sync.status_code == 200 and sync.json()["source"] == "demo" and sync.json()["inserted_count"] == 3
    # Repeating the sync upserts existing IDs without increasing the row count.
    again = await test_client.post("/api/v1/paypal/sync", headers=headers, json={"workspace_id": workspace_id, "start_date": "2026-01-01T00:00:00Z", "end_date": "2026-01-31T00:00:00Z"})
    assert again.json()["updated_count"] == 3 and again.json()["inserted_count"] == 0
    listing = await test_client.get(f"/api/v1/ledger?workspace_id={workspace_id}&page_size=2", headers=headers)
    assert listing.status_code == 200 and listing.json()["total"] == 3 and len(listing.json()["entries"]) == 2
    assert isinstance(listing.json()["entries"][0]["amount"], str)
    summary = await test_client.get(f"/api/v1/ledger/summary?workspace_id={workspace_id}", headers=headers)
    assert summary.status_code == 200 and len(summary.json()["summaries"]) == 2
    detail_id = listing.json()["entries"][0]["id"]
    detail = await test_client.get(f"/api/v1/ledger/{detail_id}?workspace_id={workspace_id}", headers=headers)
    assert detail.status_code == 200 and "raw_metadata" not in detail.json()
    outsider = await test_client.post("/api/v1/auth/register", json={"email": "out@example.com", "password": "StrongPassword123!", "full_name": "Other", "workspace_name": "Other"})
    outsider_login = await test_client.post("/api/v1/auth/login", json={"email": "out@example.com", "password": "StrongPassword123!"})
    outsider_headers = {"Authorization": f"Bearer {outsider_login.json()['access_token']}"}
    hidden = await test_client.get(f"/api/v1/ledger/{detail_id}?workspace_id={workspace_id}", headers=outsider_headers)
    assert hidden.status_code == 404
    missing_auth = await test_client.get(f"/api/v1/ledger?workspace_id={workspace_id}")
    assert missing_auth.status_code == 401


@pytest.mark.asyncio
async def test_sandbox_sync_requires_verified_connection(test_client):
    from app.core.config import get_settings

    response = await test_client.post("/api/v1/auth/register", json={"email": "sandbox@example.com", "password": "StrongPassword123!", "full_name": "Sandbox", "workspace_name": "Sandbox"})
    login = await test_client.post("/api/v1/auth/login", json={"email": "sandbox@example.com", "password": "StrongPassword123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    workspace_id = response.json()["workspace"]["id"]
    body = {"workspace_id": workspace_id, "start_date": "2026-01-01T00:00:00Z", "end_date": "2026-01-02T00:00:00Z"}
    result = await test_client.post("/api/v1/paypal/sync", headers=headers, json=body)
    assert result.status_code in (409, 503)  # no connected merchant / no configured credentials


@pytest.mark.asyncio
async def test_ledger_date_direction_filters_and_external_id_constraint(test_client):
    registration = await test_client.post("/api/v1/auth/register", json={"email": "filter@example.com", "password": "StrongPassword123!", "full_name": "Filter", "workspace_name": "Filter"})
    login = await test_client.post("/api/v1/auth/login", json={"email": "filter@example.com", "password": "StrongPassword123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    workspace_id = UUID(registration.json()["workspace"]["id"])
    session_factory = test_client._transport.app.state.test_session_factory
    async with session_factory() as session:
        row = LedgerEntry(
            workspace_id=workspace_id,
            provider="paypal",
            external_transaction_id="duplicate-key",
            transaction_type="T0006",
            status="completed",
            direction="expense",
            amount=Decimal("999.99"),
            currency="USD",
            occurred_at=datetime(2026, 2, 1, tzinfo=UTC),
            raw_metadata={},
        )
        session.add(row)
        await session.commit()
        session.add(LedgerEntry(
            workspace_id=workspace_id,
            provider="paypal",
            external_transaction_id="duplicate-key",
            transaction_type="T0006",
            status="completed",
            direction="expense",
            amount=Decimal("999.99"),
            currency="USD",
            occurred_at=datetime(2026, 2, 1, tzinfo=UTC),
            raw_metadata={},
        ))
        with pytest.raises(IntegrityError):
            await session.commit()
    filtered = await test_client.get(
        f"/api/v1/ledger?workspace_id={workspace_id}&direction=expense&start_date=2026-01-31T00:00:00Z&end_date=2026-02-02T00:00:00Z",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["entries"][0]["amount"] == "999.99"
