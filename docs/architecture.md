# GigBridge backend architecture

The backend is a modular FastAPI application. HTTP assembly lives in
`backend/app/main.py`; API routes, schemas, SQLAlchemy models, configuration,
security utilities, and database access remain in separate packages.

## Database schema

Alembic owns schema changes. The initial revision is `0001_initial` and creates
three PostgreSQL tables:

- `users`: UUID primary key, unique indexed email, Argon2 password hash, optional
  full name, active and verified flags, and timezone-aware creation/update times.
- `workspaces`: UUID primary key, required owner foreign key, name, ISO-style
  three-letter currency (defaults to USD), timezone name (defaults to UTC), and
  timezone-aware creation/update times.
- `workspace_members`: UUID primary key, workspace and user foreign keys, a
  checked `owner` or `member` role, creation time, and a unique constraint on
  `(workspace_id, user_id)`.

One user may own multiple workspaces. Each workspace has one owner and can have
multiple members. Membership rows form the many-to-many relationship between
users and workspaces. Workspace-specific reads and writes first resolve the
current user's membership; inaccessible workspaces return 404. Only owners can
change workspace settings.

Run migration commands from `backend/` after setting a real PostgreSQL
`DATABASE_URL` in `.env`:

```bash
alembic upgrade head
alembic current
alembic downgrade -1
```

The downgrade drops the tables introduced by this initial revision and their
contents. Back up data before downgrading a database that contains application
records.

## Authentication flow

Registration validates the email and password, hashes the password with
Argon2, and creates the user, owner workspace, and owner membership in one
database transaction. Login verifies the submitted password and returns a
signed JWT access token. Protected endpoints read a Bearer token, verify its
signature and expiry, load the user, and reject inactive accounts. Password
hashes and token values are never included in responses or application logs.

Set these variables in `backend/.env` (the example file contains placeholders):

- `JWT_SECRET_KEY`: private random signing key of at least 32 characters.
- `JWT_ALGORITHM`: signing algorithm; defaults to `HS256`.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: access token lifetime; defaults to 30 minutes.
- `DATABASE_URL`: PostgreSQL URL using the `postgresql+asyncpg` driver.
- `FRONTEND_URL`: allowed browser origin for CORS.

## API endpoints

All application endpoints are under `/api/v1`:

| Method | Path | Authentication | Purpose |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | No | Create a user and owner workspace. |
| `POST` | `/auth/login` | No | Exchange credentials for an access token. |
| `GET` | `/auth/me` | Bearer token | Return user and workspace memberships. |
| `GET` | `/workspaces` | Bearer token | List the user's workspaces. |
| `GET` | `/workspaces/{workspace_id}` | Bearer token + membership | Read one accessible workspace. |
| `PATCH` | `/workspaces/{workspace_id}` | Bearer token + owner role | Update name, currency, or timezone. |

Example registration request:

```json
{
  "email": "freelancer@example.com",
  "password": "StrongPassword123!",
  "full_name": "Alex Morgan",
  "workspace_name": "Alex Freelance"
}
```

Registration returns safe user and workspace fields; the password hash is not
serialized. Login returns:

```json
{
  "access_token": "<signed-jwt>",
  "token_type": "bearer",
  "expires_in": 1800
}
```

Use `Authorization: Bearer <access_token>` for protected routes. API errors
retain the shared `code`, `message`, and `request_id` JSON envelope. Swagger UI
is available at `/docs` and the OpenAPI schema at `/openapi.json`.

## Tests

Pytest uses a fresh in-memory SQLite database and enables SQLite foreign-key
checks for tests. It does not use the configured PostgreSQL database. PostgreSQL
remains the only application database and migration target.
