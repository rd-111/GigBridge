"""Async PayPal REST client for the documented Sandbox reporting APIs."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.paypal.auth import BALANCE_SCOPE, TRANSACTION_SCOPE, PayPalOAuth
from app.integrations.paypal.exceptions import (
    PayPalAPIError,
    PayPalAuthenticationError,
    PayPalInvalidResponseError,
    PayPalPermissionError,
    PayPalRateLimitError,
    PayPalTimeoutError,
    PayPalUnavailableError,
)
from app.integrations.paypal.schemas import PayPalBalance, PayPalCapabilities, PayPalTransaction
from app.integrations.paypal.transactions import normalize_transaction


class PayPalAPIClient:
    """Share one httpx client and cached app token across PayPal requests."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.http = httpx.AsyncClient(
            base_url=settings.paypal_base_url,
            timeout=settings.paypal_timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json"},
        )
        self.oauth = PayPalOAuth(self.http, settings)

    async def close(self) -> None:
        await self.http.aclose()

    async def capabilities(self) -> PayPalCapabilities:
        token = await self.oauth.get_token()
        return PayPalCapabilities(
            application_oauth_available=True,
            transaction_reporting_available=TRANSACTION_SCOPE in token.scopes,
            balance_retrieval_available=BALANCE_SCOPE in token.scopes,
            merchant_connection_supported=False,
            sandbox_mode=True,
        )

    async def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        for attempt in range(2):
            token = await self.oauth.get_token(force_refresh=attempt == 1)
            try:
                response = await self.http.get(
                    path, params=params, headers={"Authorization": f"Bearer {token.access_token}"}
                )
            except httpx.TimeoutException as exc:
                raise PayPalTimeoutError("PayPal request timed out.") from exc
            except httpx.HTTPError as exc:
                raise PayPalUnavailableError("PayPal API is unavailable.") from exc
            if response.status_code == 401 and attempt == 0:
                continue
            self._raise_for_status(response)
            try:
                body = response.json()
            except ValueError:
                raise PayPalInvalidResponseError("PayPal returned an invalid response.") from None
            if not isinstance(body, dict):
                raise PayPalInvalidResponseError("PayPal returned an invalid response.")
            return body
        raise PayPalAuthenticationError("PayPal rejected the application access token.")

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise PayPalAuthenticationError("PayPal rejected the application access token.")
        if response.status_code == 403:
            raise PayPalPermissionError("The PayPal application lacks permission for this capability.")
        if response.status_code == 429:
            raise PayPalRateLimitError("PayPal rate limit reached; retry later.")
        if response.status_code >= 500:
            raise PayPalUnavailableError("PayPal API is unavailable.")
        if response.is_error:
            raise PayPalAPIError("PayPal could not complete the request.")

    async def transactions(
        self, start: datetime, end: datetime, *, max_pages: int = 10, page_size: int = 100
    ) -> list[PayPalTransaction]:
        token = await self.oauth.get_token()
        if TRANSACTION_SCOPE not in token.scopes:
            raise PayPalPermissionError("Transaction reporting permission is not available to this application.")
        results: list[PayPalTransaction] = []
        total_pages: int | None = None
        for page in range(1, max_pages + 1):
            body = await self._get_json(
                "/v1/reporting/transactions",
                {
                    "start_date": start.isoformat().replace("+00:00", "Z"),
                    "end_date": end.isoformat().replace("+00:00", "Z"),
                    "fields": "transaction_info,payer_info",
                    "page": str(page),
                    "page_size": str(page_size),
                    "balance_affecting_records_only": "Y",
                },
            )
            rows = body.get("transaction_details")
            if not isinstance(rows, list):
                raise PayPalInvalidResponseError("PayPal returned an invalid transaction listing.")
            try:
                results.extend(normalize_transaction(row) for row in rows)
            except (TypeError, AttributeError):
                raise PayPalInvalidResponseError("PayPal returned an invalid transaction record.") from None
            # PayPal response includes total_pages; missing pagination metadata means one page.
            if total_pages is None:
                try:
                    total_pages = int(body.get("total_pages", 1))
                except (TypeError, ValueError):
                    raise PayPalInvalidResponseError("PayPal returned invalid pagination metadata.") from None
                if total_pages < 1:
                    raise PayPalInvalidResponseError("PayPal returned invalid pagination metadata.")
            if page >= total_pages:
                return results
        if total_pages and total_pages > max_pages:
            raise PayPalAPIError("The requested PayPal period contains too many pages to sync safely.")
        return results

    async def balances(self) -> list[PayPalBalance]:
        token = await self.oauth.get_token()
        if BALANCE_SCOPE not in token.scopes:
            raise PayPalPermissionError("Balance retrieval permission is not available to this application.")
        body = await self._get_json("/v1/reporting/balances", {})
        balances = body.get("balances")
        if not isinstance(balances, list):
            raise PayPalInvalidResponseError("PayPal returned an invalid balance response.")
        result = []
        try:
            for item in balances:
                currency = item["currency"]
                total = Decimal(item["total_balance"]["value"])
                available = item.get("available_balance", {}).get("value")
                withheld = item.get("withheld_balance", {}).get("value")
                result.append(
                    PayPalBalance(
                        currency,
                        total,
                        Decimal(available) if available else None,
                        Decimal(withheld) if withheld else None,
                    )
                )
        except (KeyError, TypeError, InvalidOperation):
            raise PayPalInvalidResponseError("PayPal returned an invalid balance response.") from None
        return result
