# OmniAgent Backend (Phase 3)

FastAPI service that routes allowlisted tasks from the Flutter app to a
connected Windows PC agent over an authenticated WebSocket.

In-memory storage only. No Gemini, PostgreSQL, or arbitrary remote control.

## Install

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

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
- `POST /v1/agents/register` (agent token)
- `GET /v1/agents` (app token)
- `WS /v1/agents/{id}/ws?token=...`
- `POST /v1/tasks` — `{ "instruction": "Open Notepad and type Hello from OmniAgent" }`
- `GET /v1/tasks`
- `GET /v1/tasks/{id}`
- `GET /v1/tasks/{id}/screenshot`
- `POST /v1/tasks/{id}/cancel`

Only `open notepad` instructions are accepted. Other commands are rejected.
