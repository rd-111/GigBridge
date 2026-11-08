"""Safe, typed failures from PayPal integration calls."""


class PayPalError(Exception):
    """Base class for provider failures; messages are safe for application mapping."""


class PayPalConfigurationError(PayPalError):
    """Required Sandbox credentials are absent or incomplete."""


class PayPalAuthenticationError(PayPalError):
    """PayPal rejected client credentials or an access token."""


class PayPalAPIError(PayPalError):
    """PayPal returned an unsuccessful or invalid API response."""


class PayPalRateLimitError(PayPalAPIError):
    """PayPal rate limited the request."""


class PayPalTimeoutError(PayPalAPIError):
    """The PayPal request exceeded its configured timeout."""


class PayPalUnavailableError(PayPalAPIError):
    """PayPal could not be reached or returned a server failure."""


class PayPalPermissionError(PayPalAPIError):
    """The app token lacks the scope needed for the requested capability."""


class PayPalInvalidResponseError(PayPalAPIError):
    """PayPal returned a response that does not match the expected schema."""


class PayPalConnectionRequiredError(PayPalError):
    """No verified PayPal merchant connection exists for this workspace."""
