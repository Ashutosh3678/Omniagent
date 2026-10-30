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

Default tokens (override with env vars):

- `OMNIAGENT_APP_TOKEN=dev-app-token`
- `OMNIAGENT_AGENT_TOKEN=dev-agent-token`

## Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

## API

- `GET /health`
- `POST /api/v1/agents/register` (agent token)
- `GET /api/v1/agents` (app token)
- `WS /api/v1/agents/{id}/ws?token=...`
- `POST /api/v1/tasks` — `{ "instruction": "Open Notepad and type Hello from OmniAgent" }`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{id}`
- `GET /api/v1/tasks/{id}/screenshot`
- `POST /api/v1/tasks/{id}/cancel`

Only `open notepad` instructions are accepted. Other commands are rejected.
