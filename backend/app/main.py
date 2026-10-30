"""OmniAgent FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import agents, auth, tasks
from app.store import store
from app.ws import router as ws_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.mark_all_offline()
    yield


app = FastAPI(title="OmniAgent", version="0.4.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(ws_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
