"""Orchestrate PayPal adapters, tenant checks, and normalized ledger persistence."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.paypal.client import PayPalAPIClient
from app.integrations.paypal.demo import DemoPayPalProvider
from app.integrations.paypal.exceptions import PayPalConnectionRequiredError
from app.integrations.paypal.exceptions import PayPalError
from app.integrations.paypal.schemas import PayPalCapabilities, PayPalTransaction
from app.models.paypal import LedgerEntry, PayPalConnection


class PayPalService:
    """Tenant-scoped PayPal operations; HTTP routes stay thin."""

    def __init__(self, session: AsyncSession, settings: Settings, client: PayPalAPIClient) -> None:
        self.session = session
        self.settings = settings
        self.client = client
        self.demo = DemoPayPalProvider()

    async def capabilities(self) -> PayPalCapabilities:
        if self.settings.paypal_mode == "demo":
            return self.demo.capabilities()
        return await self.client.capabilities()

    async def sync(
        self, workspace_id: UUID, start: datetime, end: datetime
    ) -> dict[str, int | str | datetime]:
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("The date range must use timezone-aware timestamps and start before end.")
        if end - start > timedelta(days=31):
            raise ValueError("The date range cannot exceed 31 days.")
        now = datetime.now(timezone.utc)
        if end > now + timedelta(minutes=5):
            raise ValueError("The end date cannot be in the future.")

        is_demo = self.settings.paypal_mode == "demo"
        provider = "demo" if is_demo else "paypal"
        connection = await self.session.scalar(
            select(PayPalConnection).where(
                PayPalConnection.workspace_id == workspace_id,
                PayPalConnection.provider == "paypal",
            )
        )
        if not is_demo and (
            connection is None
            or connection.connection_status not in {"connected", "error"}
            or not connection.merchant_id
        ):
            raise PayPalConnectionRequiredError(
                "This workspace has no verified PayPal merchant connection."
            )

        try:
            transactions = (
                self.demo.transactions(start, end)
                if is_demo
                else await self.client.transactions(start, end)
            )
        except PayPalError as exc:
            if connection is not None and not is_demo:
                connection.connection_status = "error"
                connection.last_error = str(exc)[:300]
                await self.session.commit()
            raise
        inserted, updated, skipped = await self._upsert(workspace_id, provider, transactions)
        synced_at = datetime.now(timezone.utc)
        if connection is not None and not is_demo:
            connection.last_synced_at = synced_at
            connection.last_error = None
            connection.connection_status = "connected"
        await self.session.commit()
        return {
            "status": "completed",
            "fetched_count": len(transactions),
            "inserted_count": inserted,
            "updated_count": updated,
            "skipped_count": skipped,
            "last_synced_at": synced_at,
            "source": provider,
        }

    async def _upsert(
        self, workspace_id: UUID, provider: str, transactions: list[PayPalTransaction]
    ) -> tuple[int, int, int]:
        # Deduplicate within the provider response before writing. None external IDs are not
        # expected from the adapters; database NULL uniqueness remains naturally non-conflicting.
        unique: dict[str, PayPalTransaction] = {}
        for item in transactions:
            unique[item.external_transaction_id] = item
        keys = list(unique)
        existing = set(
            (await self.session.scalars(
                select(LedgerEntry.external_transaction_id).where(
                    LedgerEntry.workspace_id == workspace_id,
                    LedgerEntry.provider == provider,
                    LedgerEntry.external_transaction_id.in_(keys),
                )
            )).all()
        ) if keys else set()
        inserted, updated = 0, 0
        for key, item in unique.items():
            values = {
                "workspace_id": workspace_id,
                "provider": provider,
                "external_transaction_id": key,
                "transaction_type": item.transaction_type,
                "status": item.status,
                "direction": item.direction,
                "amount": item.amount,
                "currency": item.currency,
                "description": item.description,
                "counterparty_name": item.counterparty_name,
                "counterparty_email": item.counterparty_email,
                "occurred_at": item.occurred_at,
                "raw_metadata": item.raw_metadata,
            }
            dialect = self.session.bind.dialect.name if self.session.bind else "postgresql"
            insert = sqlite_insert if dialect == "sqlite" else pg_insert
            statement = insert(LedgerEntry).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=["workspace_id", "provider", "external_transaction_id"],
                set_={
                    **{
                        key: getattr(statement.excluded, key)
                        for key in values
                        if key not in {"workspace_id", "provider", "external_transaction_id"}
                    },
                    "updated_at": func.now(),
                },
            )
            await self.session.execute(statement)
            if key in existing:
                updated += 1
            else:
                inserted += 1
        await self.session.flush()
        return inserted, updated, len(transactions) - len(unique)
