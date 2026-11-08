"""OAuth 2.0 client-credentials token retrieval and in-memory caching."""

import asyncio
import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.integrations.paypal.exceptions import (
    PayPalAuthenticationError,
    PayPalConfigurationError,
    PayPalInvalidResponseError,
    PayPalTimeoutError,
    PayPalUnavailableError,
)

TRANSACTION_SCOPE = "https://uri.paypal.com/services/reporting/search/read"
BALANCE_SCOPE = "https://uri.paypal.com/services/reporting/balances/read"


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    expires_at: float
    scopes: frozenset[str]


class PayPalOAuth:
    """Obtains and reuses short-lived app tokens in process memory only."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._token: OAuthToken | None = None
        self._lock = asyncio.Lock()

    async def get_token(self, *, force_refresh: bool = False) -> OAuthToken:
        if not self._settings.paypal_client_id or not self._settings.paypal_client_secret:
            raise PayPalConfigurationError("PayPal Sandbox credentials are not configured.")
        async with self._lock:
            now = time.monotonic()
            if not force_refresh and self._token and now < self._token.expires_at - 60:
                return self._token
            try:
                response = await self._http.post(
                    "/v1/oauth2/token",
                    auth=(
                        self._settings.paypal_client_id.get_secret_value(),
                        self._settings.paypal_client_secret.get_secret_value(),
                    ),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json"},
                )
            except httpx.TimeoutException as exc:
                raise PayPalTimeoutError("PayPal OAuth request timed out.") from exc
            except httpx.HTTPError as exc:
                raise PayPalUnavailableError("PayPal OAuth service is unavailable.") from exc

            if response.status_code in (400, 401):
                raise PayPalAuthenticationError("PayPal rejected the configured application credentials.")
            if response.status_code >= 500:
                raise PayPalUnavailableError("PayPal OAuth service is unavailable.")
            if response.is_error:
                raise PayPalAuthenticationError("PayPal OAuth authorization failed.")
            try:
                payload = response.json()
                token = payload["access_token"]
                lifetime = int(payload["expires_in"])
                scopes_value = payload.get("scope", "")
                scopes = frozenset(scopes_value.split()) if isinstance(scopes_value, str) else frozenset()
                if not isinstance(token, str) or not token or lifetime <= 0:
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                raise PayPalInvalidResponseError("PayPal returned an invalid OAuth response.") from None
            self._token = OAuthToken(token, time.monotonic() + lifetime, scopes)
            return self._token
