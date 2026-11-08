# GigBridge

GigBridge is a cash-flow monitoring backend for freelancers. This phase adds a
PayPal Sandbox Reporting API adapter and a PostgreSQL transaction ledger. It
does not execute payments, forecast balances, or generate AI recovery plans.

## Local setup

Requirements: Python 3.12 and PostgreSQL.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Set `DATABASE_URL` to a PostgreSQL `postgresql+asyncpg://...` URL and
`JWT_SECRET_KEY` to a private random value of at least 32 characters. Configure
`FRONTEND_URL` for CORS. `.env` is ignored by Git and must not be committed.

Set `PAYPAL_MODE=demo` to use deterministic, explicitly labeled demo ledger
rows without contacting PayPal. For Sandbox API calls, set
`PAYPAL_MODE=sandbox`, then set `PAYPAL_CLIENT_ID` and
`PAYPAL_CLIENT_SECRET` from a PayPal Sandbox REST app. The app OAuth token alone
does not connect a user merchant account: reporting access requires the needed
PayPal permission, and real sync also requires a verified merchant connection
record. PayPal documents transaction and balance APIs and their distinct OAuth
scopes; transaction reporting may require partner approval ([transaction
search documentation](https://developer.paypal.com/api/transaction-search/v1/),
[OAuth documentation](https://developer.paypal.com/api/rest/authentication/)).

Apply migrations from `backend/` after verifying the configured local database:

```bash
alembic upgrade head
```

Run the application from `backend/`:

```bash
uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`; Swagger UI is `/docs`. Run tests
from `backend/` with `pytest`. Tests use a fresh SQLite database with foreign
keys enabled and mocked PayPal HTTP responses; they do not use development data
or real PayPal credentials.

See [docs/architecture.md](docs/architecture.md) for table relationships,
migration history, endpoint contracts, sync behavior, and known limitations.
