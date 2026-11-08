# GigBridge backend architecture

The backend is a modular FastAPI application. API routes call application
services; services use async SQLAlchemy and a PayPal provider adapter. The
Sandbox adapter uses one shared `httpx.AsyncClient` and in-memory OAuth token
cache. No application startup code creates database tables.

## Database and migrations

Alembic revision `0001_initial` creates the `users`, `workspaces`, and
`workspace_members` tables. Revision `0002_paypal_ledger` adds:

- `paypal_connections`: one PayPal connection state per workspace/provider,
  environment/status, merchant reference, permission names, safe sync timestamp
  and error summary. OAuth tokens and client secrets are never stored here.
- `ledger_entries`: tenant-scoped normalized events with provider, nullable
  external event key, status/type/direction, `NUMERIC(14,2)` amount, original
  currency, occurrence time, limited metadata, and safe counterparty fields.

Workspace deletion cascades to its connection and ledger rows. External event
IDs are unique per workspace and provider; PostgreSQL allows multiple NULL
values, so records without external IDs do not collide. Each entry retains its
original currency. Summary totals group by currency and include completed
transactions only. Ledger response schemas intentionally omit raw metadata.

Apply and inspect migrations from `backend/`:

```bash
alembic upgrade head
alembic current
alembic downgrade -1  # drops only the tables introduced by 0002 and their data
```

Configure a verified local PostgreSQL database before applying migrations.
Tests instead create a fresh in-memory SQLite database and enable foreign-key
checks.

## PayPal Sandbox and demo modes

Configuration lives in `backend/.env` (copy `.env.example`; never commit `.env`):

- `PAYPAL_BASE_URL`: Sandbox REST origin, default
  `https://api-m.sandbox.paypal.com`.
- `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`: Sandbox REST application
  credentials. Secrets are held as Pydantic `SecretStr` values.
- `PAYPAL_ENVIRONMENT=sandbox`; live is deliberately rejected in this phase.
- `PAYPAL_MODE=sandbox` or `demo`. Demo mode is explicit and never a fallback
  after Sandbox errors.
- `PAYPAL_TIMEOUT_SECONDS`: outbound request timeout (default 20).
- `PAYPAL_WEBHOOK_ID`: reserved for a later webhook phase; no webhook listener
  is implemented here.

The Sandbox adapter requests an application token with OAuth 2.0
`client_credentials` at `POST /v1/oauth2/token`, caches it in process memory
until shortly before expiry, and sends it as a Bearer token. Transaction Search
uses `GET /v1/reporting/transactions` and the reporting search scope; balances
use `GET /v1/reporting/balances` and the separate balances scope. PayPal's
transaction search documentation specifies a maximum 31-day date range and
notes a delay of up to three hours for executed transactions to appear. Balance
data may also lag by up to three hours. The APIs may require approved reporting
scopes and PayPal partner access; capability checks report actual token scopes.
The app OAuth token demonstrates application access only. This phase has no
PayPal account-consent/linking flow, so Sandbox transaction sync and balances
remain gated until a merchant connection is verified by an approved flow.

`PAYPAL_MODE=demo` uses three stable, fictional transactions marked with
`provider=demo` and `{source: demo, fixture: true}` metadata. It does not call
PayPal and does not produce a balance. Demo rows never count as verified
PayPal data. The Sandbox adapter currently derives income/expense from the sign
of PayPal's reported amount; verify the account-perspective convention against
the approved merchant fixture before relying on categorization.

## API contracts

All routes require JWT authentication except the existing auth registration
and login routes. Every workspace operation first verifies membership; missing
and inaccessible workspaces return 404. Amounts serialize as decimal strings.

| Method | Path | Query/body | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/v1/paypal/status?workspace_id=...` | workspace query | Connection state; app OAuth never implies merchant connected. |
| `POST` | `/api/v1/paypal/permission-check?workspace_id=...` | workspace query | Checks app OAuth and reporting/balance scopes. |
| `POST` | `/api/v1/paypal/sync` | workspace ID and timezone-aware `start_date`, `end_date` | Bounded synchronous upsert (maximum 31 days). |
| `GET` | `/api/v1/paypal/balances?workspace_id=...` | workspace query | Retrieves per-currency balances only when connection and scope exist. |
| `GET` | `/api/v1/ledger` | `workspace_id`, optional date/direction/status/type filters, `page`, `page_size` | Descending paginated entries; max page size 100. |
| `GET` | `/api/v1/ledger/summary?workspace_id=...` | workspace query | Completed income/expense/net/count grouped by currency. |
| `GET` | `/api/v1/ledger/{entry_id}?workspace_id=...` | workspace query | One accessible entry, excluding internal raw metadata. |

Example sync request:

```json
{
  "workspace_id": "00000000-0000-4000-8000-000000000001",
  "start_date": "2026-01-01T00:00:00Z",
  "end_date": "2026-01-31T00:00:00Z"
}
```

Successful sync response includes actual counts and an explicit `source`:

```json
{
  "status": "completed",
  "fetched_count": 3,
  "inserted_count": 3,
  "updated_count": 0,
  "skipped_count": 0,
  "last_synced_at": "2026-11-08T10:00:00Z",
  "source": "demo"
}
```

The response above is illustrative. Permission and provider errors retain the
standard `{code, message, request_id}` envelope; raw PayPal responses, secrets,
tokens, and internal transaction metadata are not returned.

## Authentication and local run

Set `DATABASE_URL`, `JWT_SECRET_KEY`, and optionally `FRONTEND_URL`. Run
`alembic upgrade head`, then `uvicorn app.main:app --reload` from `backend/`.
Swagger is served at `/docs`; requests use `Authorization: Bearer <JWT>`.

Existing Phase 2 registration/login, `GET /auth/me`, and membership-protected
workspace routes remain unchanged. Authentication uses Argon2 password hashes
and short-lived signed JWT access tokens.
