# GigBridge

GigBridge is a cash-flow monitoring and recovery planning project for
freelancers. The backend currently includes the Phase 1 foundation and Phase 2
database models, migrations, JWT authentication, and workspace access control.
Forecasting, recovery plans, and PayPal actions are not implemented yet.

## Backend setup

Requirements: Python 3.12 and a PostgreSQL database.

From the repository root, create and activate a virtual environment, then
install the backend dependencies:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set `DATABASE_URL` to your PostgreSQL connection string,
`FRONTEND_URL` to the frontend origin, and `JWT_SECRET_KEY` to a private random
value of at least 32 characters. `JWT_ALGORITHM` defaults to `HS256` and
`ACCESS_TOKEN_EXPIRE_MINUTES` defaults to `30`. The API requires these settings;
the example values are placeholders. Do not commit `.env`.

Create the schema from `backend/`:

```bash
alembic upgrade head
```

The initial revision creates `users`, `workspaces`, and `workspace_members`.
See [docs/architecture.md](docs/architecture.md) for columns, relationships,
migration commands, authentication behavior, and API examples.

Run the API from `backend/`:

```bash
uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`. Swagger UI is at `/docs`, liveness
is at `/health/live`, and readiness (which checks PostgreSQL) is at
`/health/ready`.

Authentication endpoints are under `/api/v1/auth`: `POST /register`,
`POST /login`, and authenticated `GET /me`. Workspace endpoints are
`GET /api/v1/workspaces`, `GET /api/v1/workspaces/{workspace_id}`, and owner-only
`PATCH /api/v1/workspaces/{workspace_id}`. Send JWTs as
`Authorization: Bearer <access_token>`.

Run tests from `backend/` with:

```bash
pytest
```

See [docs/architecture.md](docs/architecture.md) for the backend structure.
