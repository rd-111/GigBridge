"""Add PayPal connection state and normalized transaction ledger.

Revision ID: 0002_paypal_ledger
Revises: 0001_initial
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_paypal_ledger"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paypal_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="paypal", nullable=False),
        sa.Column("environment", sa.String(length=16), server_default="sandbox", nullable=False),
        sa.Column("connection_status", sa.String(length=16), server_default="disconnected", nullable=False),
        sa.Column("merchant_id", sa.String(length=128), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider = 'paypal'", name="ck_paypal_connections_provider"),
        sa.CheckConstraint("environment IN ('sandbox', 'live')", name="ck_paypal_connections_environment"),
        sa.CheckConstraint("connection_status IN ('disconnected', 'connected', 'error')", name="ck_paypal_connections_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "provider", name="uq_paypal_connections_workspace_provider"),
    )
    op.create_index("ix_paypal_connections_workspace_id", "paypal_connections", ["workspace_id"])
    op.create_index("ix_paypal_connections_workspace_status", "paypal_connections", ["workspace_id", "connection_status"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="paypal", nullable=False),
        sa.Column("external_transaction_id", sa.String(length=255), nullable=True),
        sa.Column("transaction_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("counterparty_name", sa.String(length=200), nullable=True),
        sa.Column("counterparty_email", sa.String(length=254), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider IN ('paypal', 'demo')", name="ck_ledger_provider"),
        sa.CheckConstraint("direction IN ('income', 'expense')", name="ck_ledger_direction"),
        sa.CheckConstraint("amount >= 0", name="ck_ledger_amount_nonnegative"),
        sa.CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_ledger_currency"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "provider", "external_transaction_id", name="uq_ledger_workspace_provider_external"),
    )
    op.create_index("ix_ledger_entries_workspace_id", "ledger_entries", ["workspace_id"])
    op.create_index("ix_ledger_entries_occurred_at", "ledger_entries", ["occurred_at"])
    op.create_index("ix_ledger_entries_workspace_occurred", "ledger_entries", ["workspace_id", "occurred_at"])
    op.create_index("ix_ledger_entries_workspace_status", "ledger_entries", ["workspace_id", "status"])
    op.create_index("ix_ledger_entries_workspace_type", "ledger_entries", ["workspace_id", "transaction_type"])


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_workspace_type", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_workspace_status", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_workspace_occurred", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_occurred_at", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_workspace_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("ix_paypal_connections_workspace_status", table_name="paypal_connections")
    op.drop_index("ix_paypal_connections_workspace_id", table_name="paypal_connections")
    op.drop_table("paypal_connections")
