"""Deterministic demo provider, kept clearly separate from PayPal Sandbox data."""

from datetime import datetime, timezone
from decimal import Decimal

from app.integrations.paypal.schemas import PayPalCapabilities, PayPalTransaction


class DemoPayPalProvider:
    """Small repeatable fixture set for frontend demos; no PayPal calls are made."""

    def capabilities(self) -> PayPalCapabilities:
        return PayPalCapabilities(
            application_oauth_available=False,
            transaction_reporting_available=False,
            balance_retrieval_available=False,
            merchant_connection_supported=False,
            sandbox_mode=False,
            demo_mode=True,
        )

    def transactions(self, start: datetime, end: datetime) -> list[PayPalTransaction]:
        fixtures = [
            PayPalTransaction("demo-in-001", "DEMO_INCOME", "completed", "income", Decimal("1250.00"), "USD", datetime(2026, 1, 8, 10, tzinfo=timezone.utc), "Demo client payment", "Sample Client", None, {"source": "demo", "fixture": True}),
            PayPalTransaction("demo-out-001", "DEMO_EXPENSE", "completed", "expense", Decimal("84.50"), "USD", datetime(2026, 1, 9, 12, tzinfo=timezone.utc), "Demo software cost", "Sample Vendor", None, {"source": "demo", "fixture": True}),
            PayPalTransaction("demo-in-002", "DEMO_INCOME", "completed", "income", Decimal("430.25"), "EUR", datetime(2026, 1, 10, 9, tzinfo=timezone.utc), "Demo project milestone", "Sample Studio", None, {"source": "demo", "fixture": True}),
        ]
        return [item for item in fixtures if start <= item.occurred_at <= end]
