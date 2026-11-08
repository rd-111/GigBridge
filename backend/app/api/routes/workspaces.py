"""Tenant-isolated workspace endpoints."""

from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    CurrentWorkspaceMembership,
    WorkspaceOwnerMembership,
)
from app.models import Workspace, WorkspaceMember
from app.schemas.workspace import WorkspaceResponse, WorkspaceUpdateRequest

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(current_user: CurrentUser, session: DbSession) -> list[WorkspaceResponse]:
    """List workspaces for which the authenticated user has membership."""

    result = await session.scalars(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == current_user.id)
        .order_by(Workspace.created_at)
    )
    return [WorkspaceResponse.model_validate(workspace) for workspace in result.all()]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(membership: CurrentWorkspaceMembership) -> WorkspaceResponse:
    """Return a workspace only after membership has been checked."""

    return WorkspaceResponse.model_validate(membership.workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdateRequest,
    membership: WorkspaceOwnerMembership,
    session: DbSession,
) -> WorkspaceResponse:
    """Update workspace settings for an owner."""

    workspace = membership.workspace
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return WorkspaceResponse.model_validate(workspace)
    for field, value in values.items():
        setattr(workspace, field, value)
    await session.commit()
    await session.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)
