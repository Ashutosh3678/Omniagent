# OmniAgent Backend (Phase 3)

FastAPI service that routes allowlisted tasks from the Flutter app to a
connected Windows PC agent over an authenticated WebSocket.

Agents, tasks and screenshots are stored in PostgreSQL (SQLAlchemy + Alembic).
No Gemini or arbitrary remote control yet.

## Install

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Database

```powershell
docker compose up -d db          # from the repo root
cd backend
alembic upgrade head
```

Connection string: `OMNIAGENT_DATABASE_URL` (default
`postgresql+psycopg://omniagent:omniagent@localhost:5432/omniagent`).
Tests use in-memory SQLite and need no database.

## Run

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Accounts use Argon2 password hashes and HS256 JWTs. Set `OMNIAGENT_JWT_SECRET`
to a long random value outside local dev (a dev default is built in).

## Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

## API

- `GET /health`
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/token` (OAuth2 form), `GET /api/v1/auth/me`
- `POST /api/v1/agents/register` (user JWT; returns the PC's device token once)
- `GET /api/v1/agents`
- `POST /api/v1/tasks` — `{ "instruction": "Open Notepad and type Hello from OmniAgent" }`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{id}`
- `GET /api/v1/tasks/{id}/screenshot`
- `POST /api/v1/tasks/{id}/cancel`

Only `open notepad` instructions are accepted. Other commands are rejected.
