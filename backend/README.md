# OmniAgent Backend (Phase 3)

FastAPI service that routes allowlisted tasks from the Flutter app to a
connected Windows PC agent over an authenticated WebSocket.

Agents, tasks and screenshots are stored in PostgreSQL (SQLAlchemy + Alembic).
No arbitrary remote control: every step is a typed, validated action.

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

## Actions and plans

A task is a plan: an ordered list of typed steps (`app/schema.py`). Each step is one of
`open_app`, `type_text`, `press_key`, `wait`, `screenshot`, `click`, `scroll`,
`browser_navigate`; extra or missing parameters are rejected. Apps are `notepad` and
`browser` (off by default; turn it on per PC with `PATCH /agents/{id}`). Browser addresses
must be public `http(s)` pages: no logins in the URL, no local or private network hosts.

What a PC can run is what its agent reports on connect (`capabilities` message, shown as
`actions` in `GET /agents`). Until an agent reports, it is treated as an older one that can
only open, type, press keys, wait and take screenshots.

`app/validation.py` checks every step: known action, valid parameters, runnable on the
PC, and inside the PC's permitted apps. The first step that fails is held back with a
reason (`unknown_action`, `invalid_parameters`, `not_supported`, `unknown_app`,
`app_not_permitted`, `no_app_open`, `plan_too_long`), and so is everything after it. Only the
clean prefix is sent; if nothing can run, the task is refused. A plan with held-back steps
ends as `partial`. Plan confidence is the mean confidence of the accepted steps.

WebSocket messages: agent to backend: `capabilities` (`actions`), `ack`, `step` (`index`,
`status`: running/success/failed/unverified/skipped, `detail`, optional JPEG
`screenshot_b64`) and `result` (`completed`/`partial`/`failed`). Backend to agent: `task`
(with `plan`) and `cancel`. `unverified` means the agent acted but could not confirm the
result on screen. Connection health uses the WebSocket protocol's own ping/pong.

Step thumbnails: `GET /api/v1/tasks/{id}/steps/{index}/screenshot`.
`POST /api/v1/tasks/{id}/cancel` marks the task cancelled and tells the agent to stop
after its current step.

## Planner (Groq)

`POST /api/v1/tasks` and `POST /api/v1/plans/preview` turn an instruction into a plan:

1. The built-in rules handle exact phrases such as "Open Notepad and type ..." (no AI call).
2. Anything else goes to an LLM on Groq (`app/planner.py`, default `openai/gpt-oss-20b`)
   when a key is configured. The request asks for a JSON object at temperature 0 and lists
   only the actions and apps this PC may use. The user's text is sent as data, never as part of the system prompt.
3. Whatever the planner returns is untrusted and goes through the same validator as every
   other plan. A planner failure is a 503 and never falls back to guessing; LLM calls
   are limited to 20 per user per minute.

`POST /api/v1/plans/preview` plans and validates without running anything and returns the
steps, held-back steps, confidence and a `low_confidence` flag. Send its `plan` back in
`POST /api/v1/tasks` to run exactly what was previewed (it is validated again).

Set the key in the environment or in an untracked `backend/.env` (or repo-root `.env`):

```
OMNIAGENT_GROQ_API_KEY=your-key
OMNIAGENT_GROQ_MODEL=openai/gpt-oss-20b   # optional
```

Your instruction text is sent to Groq's API when the rules do not match it.

## Dispatch rules

A task is sent only if every check passes, and the first failure is refused and
written to the audit log: PC exists and is yours (404), not removed (403), access
not expired (403), connected (503), then the plan is validated against the PC's
permitted apps (403 if the app is not allowed, 422 for other unrunnable plans).
Unparseable instructions are refused with 400.

## Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

## API

- `GET /health`
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/token` (OAuth2 form), `GET /api/v1/auth/me`
- `POST /api/v1/agents/pairing-code` (user JWT): one-time code, valid 10 minutes
- `POST /api/v1/agents/pair` (no login, rate limited): the PC trades the code for its device token, shown once
- `GET /api/v1/agents`, `PATCH /api/v1/agents/{id}` (name, permitted apps, expiry), `POST /api/v1/agents/{id}/revoke`
- `GET /api/v1/audit`: your dispatch and device decisions, newest first
- `POST /api/v1/tasks` — `{ "instruction": "Open Notepad and type Hello from OmniAgent" }`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{id}`
- `GET /api/v1/tasks/{id}/screenshot`
- `POST /api/v1/tasks/{id}/cancel`

Only `open notepad` instructions are accepted. Other commands are rejected.
