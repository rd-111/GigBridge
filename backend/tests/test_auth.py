"""Authentication and workspace API tests with isolated database fixtures."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models import User, Workspace, WorkspaceMember


def registration(email: str = "freelancer@example.com") -> dict[str, str]:
    return {
        "email": email,
        "password": "StrongPassword123!",
        "full_name": "Alex Morgan",
        "workspace_name": "Alex Freelance",
    }


@pytest.mark.asyncio
async def test_registration_creates_user_workspace_and_owner_membership(test_client):
    response = await test_client.post("/api/v1/auth/register", json=registration())
    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == "freelancer@example.com"
    assert "hashed_password" not in payload["user"]
    assert payload["workspace"]["name"] == "Alex Freelance"
    assert payload["workspace"]["role"] == "owner"

    session_factory = test_client._transport.app.state.test_session_factory
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "freelancer@example.com"))
        assert user is not None and user.hashed_password != registration()["password"]
        workspace = await session.get(Workspace, UUID(payload["workspace"]["id"]))
        assert workspace is not None
        membership = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == user.id,
            )
        )
        assert membership is not None and membership.role == "owner"


@pytest.mark.asyncio
async def test_duplicate_email_returns_conflict(test_client):
    await test_client.post("/api/v1/auth/register", json=registration())
    response = await test_client.post("/api/v1/auth/register", json=registration())
    assert response.status_code == 409
    assert response.json()["code"] == "HTTP_ERROR"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {**registration(), "email": "not-an-email"},
        {**registration(), "password": "weak"},
    ],
)
async def test_registration_validates_email_and_password(test_client, payload):
    response = await test_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_login_returns_access_token(test_client):
    await test_client.post("/api/v1/auth/register", json=registration())
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "freelancer@example.com", "password": "StrongPassword123!"},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["expires_in"] > 0
    assert response.json()["access_token"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "email,password",
    [
        ("freelancer@example.com", "WrongPassword123!"),
        ("unknown@example.com", "WrongPassword123!"),
    ],
)
async def test_login_rejects_bad_credentials_generically(test_client, email, password):
    await test_client.post("/api/v1/auth/register", json=registration())
    response = await test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json()["message"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_login_rejects_inactive_account(test_client):
    await test_client.post("/api/v1/auth/register", json=registration())
    session_factory = test_client._transport.app.state.test_session_factory
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "freelancer@example.com"))
        user.is_active = False
        await session.commit()
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "freelancer@example.com", "password": "StrongPassword123!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_valid_token_and_returns_workspaces(test_client):
    missing = await test_client.get("/api/v1/auth/me")
    assert missing.status_code == 401
    await test_client.post("/api/v1/auth/register", json=registration())
    login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "freelancer@example.com", "password": "StrongPassword123!"},
    )
    token = login.json()["access_token"]
    response = await test_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert len(response.json()["workspaces"]) == 1
    assert "hashed_password" not in response.json()
    invalid = await test_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer malformed"})
    assert invalid.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_is_rejected(test_client):
    payload = {"sub": str(uuid4()), "exp": datetime.now(UTC) - timedelta(minutes=1)}
    settings = get_settings()
    expired_token = jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)
    response = await test_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_workspace_membership_and_owner_permissions(test_client):
    await test_client.post("/api/v1/auth/register", json=registration())
    login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "freelancer@example.com", "password": "StrongPassword123!"},
    )
    owner_token = login.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    listing = await test_client.get("/api/v1/workspaces", headers=owner_headers)
    workspace_id = listing.json()[0]["id"]
    assert (await test_client.get(f"/api/v1/workspaces/{workspace_id}", headers=owner_headers)).status_code == 200
    assert (
        await test_client.patch(
            f"/api/v1/workspaces/{workspace_id}",
            headers=owner_headers,
            json={"name": "Updated Workspace", "currency": "EUR"},
        )
    ).status_code == 200

    session_factory = test_client._transport.app.state.test_session_factory
    member = User(email="member@example.com", hashed_password=hash_password("MemberPassword123!"))
    async with session_factory() as session:
        owner = await session.scalar(select(User).where(User.email == "freelancer@example.com"))
        workspace = await session.get(Workspace, UUID(workspace_id))
        session.add(member)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=member.id, role="member"))
        await session.commit()
        member_id = member.id
    async with session_factory() as session:
        member = await session.get(User, member_id)
        member_token, _ = create_access_token(member.id)
    member_headers = {"Authorization": f"Bearer {member_token}"}
    assert (await test_client.get(f"/api/v1/workspaces/{workspace_id}", headers=member_headers)).status_code == 200
    denied = await test_client.patch(
        f"/api/v1/workspaces/{workspace_id}", headers=member_headers, json={"name": "Denied"}
    )
    assert denied.status_code == 403

    outsider = User(email="outsider@example.com", hashed_password=hash_password("OutsiderPassword123!"))
    async with session_factory() as session:
        session.add(outsider)
        await session.commit()
        outsider_token, _ = create_access_token(outsider.id)
    missing = await test_client.get(
        f"/api/v1/workspaces/{workspace_id}", headers={"Authorization": f"Bearer {outsider_token}"}
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_database_unique_and_foreign_key_constraints(test_client):
    from sqlalchemy.exc import IntegrityError

    session_factory = test_client._transport.app.state.test_session_factory
    async with session_factory() as session:
        user = User(email="unique@example.com", hashed_password=hash_password("StrongPassword123!"))
        session.add(user)
        await session.commit()
        user_id = user.id
        with pytest.raises(IntegrityError):
            session.add(User(email="unique@example.com", hashed_password="hash"))
            await session.commit()
        await session.rollback()

        workspace = Workspace(name="Constraint workspace", owner_id=user_id)
        session.add(workspace)
        await session.commit()
        session.add_all(
            [
                WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role="owner"),
                WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role="owner"),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        session.add(WorkspaceMember(workspace_id=uuid4(), user_id=uuid4(), role="member"))
        with pytest.raises(IntegrityError):
            await session.commit()
