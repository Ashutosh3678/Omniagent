# OmniAgent

OmniAgent is an autonomous computer-interaction agent. A later phase will accept
a natural-language instruction such as:

> Open Notepad and type Hello from OmniAgent.

The agent will observe the screen, take actions, verify the result, and continue
until the task is done.

## Current phase

**Phase 1: Windows PC Agent (local automation only).**

A Python program on Windows can:

1. Open Notepad.
2. Type a message such as `Hello from OmniAgent`.
3. Capture a screenshot of the screen.
4. Verify that the task completed.
5. Display **Success** or **Failed**.

This phase does **not** include AI, a mobile app, a backend, a database, or
remote connectivity. The goal is reliable local Windows automation first.

## Repository structure

```text
omniagent/
├── desktop-agent/   Phase 1 Windows PC agent (Python)
├── mobile/           Flutter UI (mock data)
├── backend/          FastAPI (later)
├── docker/           Deployment (later)
└── docs/             Architecture docs (later)
```

## Run Phase 1

```powershell
cd desktop-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Full install notes and troubleshooting: [desktop-agent/README.md](desktop-agent/README.md).

## Mobile UI

Mock Flutter screens only. No backend or remote control.

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
| 2+ | Agent engine, backend, remote connectivity, mobile app, AI |
