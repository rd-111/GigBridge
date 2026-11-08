"""PayPal Sandbox and deterministic demo adapters."""

from app.integrations.paypal.client import PayPalAPIClient
from app.integrations.paypal.demo import DemoPayPalProvider
from app.integrations.paypal.exceptions import (
    PayPalAPIError,
    PayPalAuthenticationError,
    PayPalConfigurationError,
    PayPalRateLimitError,
    PayPalTimeoutError,
    PayPalUnavailableError,
)

__all__ = [
    "PayPalAPIClient",
    "DemoPayPalProvider",
    "PayPalAPIError",
    "PayPalAuthenticationError",
    "PayPalConfigurationError",
    "PayPalRateLimitError",
    "PayPalTimeoutError",
    "PayPalUnavailableError",
]
