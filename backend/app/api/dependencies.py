"""Reusable authentication and workspace authorization dependencies."""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db_session
from app.models import User, WorkspaceMember
from app.models.workspace import WorkspaceMember as Membership
from app.schemas.auth import WorkspaceSummary
from app.schemas.workspace import WorkspaceResponse
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DbSession,
) -> User:
    """Resolve a valid Bearer token to an active user."""

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized from None

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_workspace_membership(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> Membership:
    """Load membership or return not found to conceal inaccessible tenants."""

    membership = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user.id,
        ).options(selectinload(WorkspaceMember.workspace))
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return membership


CurrentWorkspaceMembership = Annotated[Membership, Depends(get_workspace_membership)]


async def require_workspace_owner(
    membership: CurrentWorkspaceMembership,
) -> Membership:
    """Require owner role for workspace settings changes."""

    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Workspace owner permission is required.")
    return membership


WorkspaceOwnerMembership = Annotated[Membership, Depends(require_workspace_owner)]


def workspace_summary(membership: Membership) -> WorkspaceSummary:
    """Build a safe workspace summary from a loaded membership."""

    workspace = membership.workspace
    return WorkspaceSummary(
        id=workspace.id,
        name=workspace.name,
        currency=workspace.currency,
        timezone=workspace.timezone,
        role=membership.role,
    )


