"""Normalized, provider-independent PayPal data shapes."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PayPalTransaction:
    external_transaction_id: str
    transaction_type: str
    status: str
    direction: str
    amount: Decimal
    currency: str
    occurred_at: datetime
    description: str | None = None
    counterparty_name: str | None = None
    counterparty_email: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PayPalBalance:
    currency: str
    total: Decimal
    available: Decimal | None = None
    withheld: Decimal | None = None


@dataclass(frozen=True)
class PayPalCapabilities:
    application_oauth_available: bool
    transaction_reporting_available: bool
    balance_retrieval_available: bool
    merchant_connection_supported: bool
    sandbox_mode: bool
    demo_mode: bool = False
