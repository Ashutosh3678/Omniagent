"""Runtime settings. Secrets default to local-dev values only."""

from __future__ import annotations

import os

JWT_SECRET = os.environ.get("OMNIAGENT_JWT_SECRET", "dev-only-secret-change-me-in-production-0000")
JWT_EXPIRE_MINUTES = int(os.environ.get("OMNIAGENT_JWT_EXPIRE_MINUTES", str(7 * 24 * 60)))
PAIRING_CODE_TTL_SECONDS = int(os.environ.get("OMNIAGENT_PAIRING_TTL", "600"))
TASK_TIMEOUT_SECONDS = float(os.environ.get("OMNIAGENT_TASK_TIMEOUT", "90"))
STEP_TIMEOUT_SECONDS = float(os.environ.get("OMNIAGENT_STEP_TIMEOUT", "30"))
HOST = os.environ.get("OMNIAGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("OMNIAGENT_PORT", "8000"))
DATABASE_URL = os.environ.get(
    "OMNIAGENT_DATABASE_URL",
    "postgresql+psycopg://omniagent:omniagent@localhost:5432/omniagent",
)
