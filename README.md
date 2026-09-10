# OmniAgent

OmniAgent is an AI-powered autonomous computer interaction agent. A user will eventually give a natural-language instruction such as:

> Open Notepad and type Hello from OmniAgent.

The agent will observe the computer screen, reason about the current state, perform actions, verify the result, and continue until the task is completed.

## Current phase

**Phase 1: Project foundation and frontend dashboard prototype.**

The Next.js dashboard is implemented with mock/local execution only. The FastAPI backend, agent engine, and Windows desktop agent are not implemented yet.

## Repository structure

```text
omniagent/
├── frontend/         Phase 1 Next.js dashboard
├── backend/          FastAPI (later)
├── desktop-agent/   Windows computer-control agent (later)
├── docker/           Deployment (later)
└── docs/             Architecture and phase docs (later)
```

## Future architecture

```text
Next.js
    ↓
FastAPI
    ↓
Agent Engine
    ↓
Desktop Agent
    ↓
Windows Computer
```

## Frontend (Phase 1)

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Roadmap

| Phase | Scope |
| --- | --- |
| 1 | Project foundation and frontend UI with mock execution |
| 2+ | FastAPI backend, agent engine, desktop agent, live screenshots, WebSockets, auth, Docker |

Do not expect computer control, LLM calls, or live screenshots in this phase.
