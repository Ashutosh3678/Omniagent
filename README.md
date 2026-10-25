# OmniAgent

OmniAgent is an autonomous computer-interaction agent. A later phase will accept
a natural-language instruction such as:

> Open Notepad and type Hello from OmniAgent.

The agent will observe the screen, take actions, verify the result, and continue
until the task is done.

## Current phase

**Phase 3: FastAPI backend and agent communication.**

A Python program on Windows can:

1. Open Notepad.
2. Type a message such as `Hello from OmniAgent`.
3. Capture a screenshot of the screen.
4. Verify that the task completed.
5. Display **Success** or **Failed**.

The Flutter app submits an allowlisted Notepad task to FastAPI. The backend
routes it over an authenticated WebSocket to the Windows PC agent. The agent
runs the existing Notepad automation and returns status, logs, and a
screenshot. Storage is in-memory. No Gemini or PostgreSQL yet.

## Repository structure

```text
omniagent/
├── desktop-agent/   Windows PC agent (Python)
├── mobile/           Flutter app
├── backend/          FastAPI
├── docker/           Deployment (later)
└── docs/             Architecture docs (later)
```

## Start Phase 3

Terminal 1 — backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Terminal 2 — Windows agent:

```powershell
cd desktop-agent
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python connect.py --api http://127.0.0.1:8000 --token dev-agent-token
```

Terminal 3 — mobile app:

```powershell
cd mobile
flutter pub get
flutter run --dart-define=API_BASE=http://127.0.0.1:8000 --dart-define=APP_TOKEN=dev-app-token
```

On an Android emulator use `API_BASE=http://10.0.2.2:8000`.

Then tap **Run Task** with `Open Notepad and type Hello from OmniAgent`.

Offline Notepad demo still works: `cd desktop-agent` then `python main.py`.

## Mobile UI

```powershell
cd mobile
flutter pub get
flutter run
```

## Future architecture

```text
Mobile / web client
    ↓
Backend
    ↓
Agent engine
    ↓
Desktop agent
    ↓
Windows PC
```

## Roadmap

| Phase | Scope |
| --- | --- |
| 1 | Local Windows agent: Notepad, typing, screenshot, verification |
| 2 | Flutter mobile UI (8 screens) |
| 3 | FastAPI backend, authenticated agent WebSocket, task status |
| 4+ | Gemini, PostgreSQL, richer actions |
