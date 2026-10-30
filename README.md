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
screenshot. Data is stored in PostgreSQL; accounts, device pairing, plan validation and an
LLM planner (Groq) sit in front of the agent.

## Repository structure

```text
omniagent/
├── desktop-agent/   Windows PC agent (Python)
├── mobile/           Flutter app
├── backend/          FastAPI
├── docker/           Deployment (later)
└── docs/             Architecture docs (later)
```

## Run it

The backend is deployed at `https://omniagent-backend-22fj.onrender.com` (see `backend/README.md` to run your
own). It sleeps when idle, so the first request after a while takes up to a minute.

1. **Phone app**: `cd mobile`, `flutter pub get`, `flutter run`. Create an account on the login screen.
2. **PC**: in `desktop-agent`, double-click `start_agent.bat` (or `python app.py`). In the app open
   **Devices > Add PC > Get pairing code**, type the code into the window, press **Connect**.
3. In the app, type a task such as `Open Notepad and type Hello from OmniAgent` and tap **Run Task**.

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
| 4 | PostgreSQL, accounts, device pairing, audit log |
| 5 | Typed multi-step plans, validation, LLM planner (Groq) with preview |
| 6+ | Observe-think-act-verify loop, richer actions, streaming, CI |
