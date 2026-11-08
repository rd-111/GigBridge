"""Tenant-isolated ledger listing and currency-specific summaries."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, func, select

from app.api.dependencies import CurrentUser, DbSession, get_workspace_membership
from app.models.paypal import LedgerEntry
from app.schemas.paypal import CurrencySummary, LedgerEntryResponse, LedgerPageResponse, LedgerSummaryResponse

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("", response_model=LedgerPageResponse)
async def list_ledger(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    direction: Literal["income", "expense"] | None = None,
    status: str | None = Query(default=None, max_length=32),
    transaction_type: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> LedgerPageResponse:
    await get_workspace_membership(workspace_id, current_user, session)
    if (start_date and start_date.tzinfo is None) or (end_date and end_date.tzinfo is None):
        raise HTTPException(status_code=400, detail="Date filters must include a timezone.")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date.")
    filters = [LedgerEntry.workspace_id == workspace_id]
    if start_date:
        filters.append(LedgerEntry.occurred_at >= start_date)
    if end_date:
        filters.append(LedgerEntry.occurred_at <= end_date)
    if direction:
        filters.append(LedgerEntry.direction == direction)
    if status:
        filters.append(LedgerEntry.status == status)
    if transaction_type:
        filters.append(LedgerEntry.transaction_type == transaction_type)
    total = await session.scalar(select(func.count()).select_from(LedgerEntry).where(*filters)) or 0
    entries = await session.scalars(
        select(LedgerEntry).where(*filters).order_by(LedgerEntry.occurred_at.desc(), LedgerEntry.id).offset((page - 1) * page_size).limit(page_size)
    )
    return LedgerPageResponse(
        entries=[LedgerEntryResponse.model_validate(entry) for entry in entries.all()],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/summary", response_model=LedgerSummaryResponse)
async def ledger_summary(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> LedgerSummaryResponse:
    await get_workspace_membership(workspace_id, current_user, session)
    rows = await session.execute(
        select(
            LedgerEntry.currency,
            func.sum(case((LedgerEntry.direction == "income", LedgerEntry.amount), else_=0)).label("income"),
            func.sum(case((LedgerEntry.direction == "expense", LedgerEntry.amount), else_=0)).label("expenses"),
            func.count(LedgerEntry.id).label("count"),
        ).where(LedgerEntry.workspace_id == workspace_id, LedgerEntry.status == "completed").group_by(LedgerEntry.currency).order_by(LedgerEntry.currency)
    )
    summaries = []
    for currency, income, expenses, count in rows.all():
        income, expenses = income or 0, expenses or 0
        summaries.append(CurrencySummary(currency=currency, total_income=income, total_expenses=expenses, net_cash_flow=income-expenses, transaction_count=count))
    return LedgerSummaryResponse(summaries=summaries)


@router.get("/{entry_id}", response_model=LedgerEntryResponse)
async def ledger_detail(
    entry_id: UUID,
    workspace_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> LedgerEntryResponse:
    await get_workspace_membership(workspace_id, current_user, session)
    entry = await session.scalar(
        select(LedgerEntry).where(LedgerEntry.id == entry_id, LedgerEntry.workspace_id == workspace_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Ledger entry not found.")
    return LedgerEntryResponse.model_validate(entry)
