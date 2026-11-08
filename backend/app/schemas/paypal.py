"""Public PayPal and ledger response/request schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PayPalStatusResponse(BaseModel):
    provider: str = "paypal"
    environment: str
    mode: Literal["sandbox", "demo"]
    connection_status: str
    merchant_id: str | None = None
    email: str | None = None
    permissions: list[str] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    last_error: str | None = None


class CapabilityResponse(BaseModel):
    application_oauth_available: bool
    transaction_reporting_available: bool
    balance_retrieval_available: bool
    merchant_connection_supported: bool
    sandbox_mode: bool
    demo_mode: bool = False


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    start_date: datetime
    end_date: datetime


class SyncResponse(BaseModel):
    status: str
    fetched_count: int
    inserted_count: int
    updated_count: int
    skipped_count: int
    last_synced_at: datetime
    source: str


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    provider: str
    external_transaction_id: str | None
    transaction_type: str
    status: str
    direction: str
    amount: Decimal
    currency: str
    description: str | None
    counterparty_name: str | None
    counterparty_email: str | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class LedgerPageResponse(BaseModel):
    entries: list[LedgerEntryResponse]
    page: int
    page_size: int
    total: int


class CurrencySummary(BaseModel):
    currency: str
    total_income: Decimal
    total_expenses: Decimal
    net_cash_flow: Decimal
    transaction_count: int


class LedgerSummaryResponse(BaseModel):
    summaries: list[CurrencySummary]


class BalanceResponse(BaseModel):
    currency: str
    total: Decimal
    available: Decimal | None = None
    withheld: Decimal | None = None
