"""Registration, login, and current-user endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession, workspace_summary
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User, Workspace, WorkspaceMember
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegistrationResponse,
    RegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
InvalidCredentials = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid email or password.",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/register", response_model=RegistrationResponse, status_code=201)
async def register(payload: RegisterRequest, session: DbSession) -> RegistrationResponse:
    """Create an account, owner workspace, and owner membership atomically."""

    existing_user = await session.scalar(select(User.id).where(User.email == str(payload.email).lower()))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=str(payload.email).lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    workspace = Workspace(name=payload.workspace_name, owner=user)
    membership = WorkspaceMember(user=user, workspace=workspace, role="owner")
    session.add_all([user, workspace, membership])
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.info("Registration rejected by a uniqueness constraint")
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from None
    await session.refresh(user)
    await session.refresh(workspace)
    safe_user = UserResponse.model_validate(user, from_attributes=True)
    return RegistrationResponse(
        user=safe_user,
        workspace={
            "id": workspace.id,
            "name": workspace.name,
            "currency": workspace.currency,
            "timezone": workspace.timezone,
            "role": "owner",
        },
    )


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: DbSession) -> LoginResponse:
    """Authenticate with a generic response for unknown users and bad passwords."""

    user = await session.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None:
        # Perform a dummy verification to make the two failure paths more similar.
        verify_password(payload.password, "$argon2id$v=19$m=65536,t=3,p=4$invalid$invalid")
        raise InvalidCredentials
    if not verify_password(payload.password, user.hashed_password):
        raise InvalidCredentials
    if not user.is_active:
        raise InvalidCredentials
    token, expires_in = create_access_token(user.id)
    return LoginResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=MeResponse)
async def get_me(current_user: CurrentUser, session: DbSession) -> MeResponse:
    """Return the authenticated user and their workspace memberships."""

    result = await session.scalars(
        select(WorkspaceMember)
        .options(selectinload(WorkspaceMember.workspace))
        .where(WorkspaceMember.user_id == current_user.id)
    )
    memberships = list(result.all())
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        workspaces=[workspace_summary(membership) for membership in memberships],
    )
