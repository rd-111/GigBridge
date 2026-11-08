"""Workspace-scoped PayPal status, capability, sync, and balance endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession, get_workspace_membership
from app.core.config import Settings, get_settings
from app.integrations.paypal.client import PayPalAPIClient
from app.integrations.paypal.exceptions import PayPalConnectionRequiredError
from app.models.paypal import PayPalConnection
from app.schemas.paypal import BalanceResponse, CapabilityResponse, PayPalStatusResponse, SyncRequest, SyncResponse
from app.services.paypal import PayPalService

router = APIRouter(prefix="/paypal", tags=["paypal"])


async def get_paypal_client(request: Request) -> PayPalAPIClient:
    """Return the shared process-level PayPal client."""
    return request.app.state.paypal_client


PayPalClient = Annotated[PayPalAPIClient, Depends(get_paypal_client)]


@router.get("/status", response_model=PayPalStatusResponse)
async def paypal_status(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PayPalStatusResponse:
    membership = await get_workspace_membership(workspace_id, current_user, session)
    connection = await session.scalar(
        select(PayPalConnection).where(PayPalConnection.workspace_id == membership.workspace_id)
    )
    return PayPalStatusResponse(
        environment=settings.paypal_environment,
        mode=settings.paypal_mode,
        connection_status=connection.connection_status if connection else "disconnected",
        merchant_id=connection.merchant_id if connection else None,
        email=connection.email if connection else None,
        permissions=connection.permissions if connection else [],
        last_synced_at=connection.last_synced_at if connection else None,
        last_error=connection.last_error if connection else None,
    )


@router.post("/permission-check", response_model=CapabilityResponse)
async def permission_check(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    client: PayPalClient,
) -> CapabilityResponse:
    await get_workspace_membership(workspace_id, current_user, session)
    capabilities = await PayPalService(session, settings, client).capabilities()
    return CapabilityResponse.model_validate(capabilities.__dict__)


@router.post("/sync", response_model=SyncResponse)
async def sync_transactions(
    payload: SyncRequest,
    current_user: CurrentUser,
    session: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    client: PayPalClient,
) -> SyncResponse:
    await get_workspace_membership(payload.workspace_id, current_user, session)
    try:
        summary = await PayPalService(session, settings, client).sync(
            payload.workspace_id, payload.start_date, payload.end_date
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except PayPalConnectionRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return SyncResponse(**summary)


@router.get("/balances", response_model=list[BalanceResponse])
async def get_balances(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    client: PayPalClient,
) -> list[BalanceResponse]:
    membership = await get_workspace_membership(workspace_id, current_user, session)
    if settings.paypal_mode == "demo":
        raise HTTPException(status_code=409, detail="Balance retrieval is unavailable in demo mode.")
    connection = await session.scalar(
        select(PayPalConnection).where(PayPalConnection.workspace_id == membership.workspace_id)
    )
    if connection is None or connection.connection_status != "connected":
        raise HTTPException(status_code=409, detail="This workspace has no verified PayPal merchant connection.")
    return [BalanceResponse(**balance.__dict__) for balance in await client.balances()]
