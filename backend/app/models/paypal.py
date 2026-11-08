"""PayPal connection and normalized financial ledger models."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PayPalConnection(Base):
    """A verified PayPal account association for one workspace."""

    __tablename__ = "paypal_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_paypal_connections_workspace_provider"),
        CheckConstraint("provider = 'paypal'", name="ck_paypal_connections_provider"),
        CheckConstraint("environment IN ('sandbox', 'live')", name="ck_paypal_connections_environment"),
        CheckConstraint(
            "connection_status IN ('disconnected', 'connected', 'error')",
            name="ck_paypal_connections_status",
        ),
        Index("ix_paypal_connections_workspace_status", "workspace_id", "connection_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="paypal", server_default="paypal", nullable=False)
    environment: Mapped[str] = mapped_column(String(16), default="sandbox", server_default="sandbox", nullable=False)
    connection_status: Mapped[str] = mapped_column(
        String(16), default="disconnected", server_default="disconnected", nullable=False
    )
    merchant_id: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(254))
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="paypal_connection")


class LedgerEntry(Base):
    """A currency-preserving normalized transaction record."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "provider", "external_transaction_id", name="uq_ledger_workspace_provider_external"
        ),
        CheckConstraint("provider IN ('paypal', 'demo')", name="ck_ledger_provider"),
        CheckConstraint("direction IN ('income', 'expense')", name="ck_ledger_direction"),
        CheckConstraint("amount >= 0", name="ck_ledger_amount_nonnegative"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_ledger_currency"),
        Index("ix_ledger_entries_workspace_occurred", "workspace_id", "occurred_at"),
        Index("ix_ledger_entries_workspace_status", "workspace_id", "status"),
        Index("ix_ledger_entries_workspace_type", "workspace_id", "transaction_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="paypal", server_default="paypal", nullable=False)
    external_transaction_id: Mapped[str | None] = mapped_column(String(255))
    transaction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    counterparty_name: Mapped[str | None] = mapped_column(String(200))
    counterparty_email: Mapped[str | None] = mapped_column(String(254))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
