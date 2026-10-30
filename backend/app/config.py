"""Runtime settings. Secrets default to local-dev values only.

Values come from the environment; a `.env` file in `backend/` or the repo root is
read too (real environment variables win). `.env` is gitignored.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent.parent
for _env in (_HERE / ".env", _HERE.parent / ".env"):
    load_dotenv(_env, override=False)

DEV_JWT_SECRET = "dev-only-secret-change-me-in-production-0000"
ENVIRONMENT = os.environ.get("OMNIAGENT_ENV", "development").lower()
JWT_SECRET = os.environ.get("OMNIAGENT_JWT_SECRET", DEV_JWT_SECRET)
JWT_EXPIRE_MINUTES = int(os.environ.get("OMNIAGENT_JWT_EXPIRE_MINUTES", str(7 * 24 * 60)))
PAIRING_CODE_TTL_SECONDS = int(os.environ.get("OMNIAGENT_PAIRING_TTL", "600"))
TASK_TIMEOUT_SECONDS = float(os.environ.get("OMNIAGENT_TASK_TIMEOUT", "90"))
STEP_TIMEOUT_SECONDS = float(os.environ.get("OMNIAGENT_STEP_TIMEOUT", "30"))
HOST = os.environ.get("OMNIAGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("OMNIAGENT_PORT", "8000"))


def normalize_database_url(url: str) -> str:
    """Hosts such as Render hand out `postgres://...` or `postgresql://...`; SQLAlchemy needs the driver named."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def check_production(environment: str, jwt_secret: str, database_url: str) -> None:
    """In production, refuse to start with settings that are only safe on a developer's machine."""
    if environment != "production":
        return
    if jwt_secret == DEV_JWT_SECRET or len(jwt_secret) < 32:
        raise RuntimeError("OMNIAGENT_JWT_SECRET must be set to a random value of at least 32 characters in production")
    if database_url.startswith("sqlite"):
        raise RuntimeError("Production needs PostgreSQL: set OMNIAGENT_DATABASE_URL (or DATABASE_URL)")


DATABASE_URL = normalize_database_url(
    os.environ.get("OMNIAGENT_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql+psycopg://omniagent:omniagent@localhost:5432/omniagent"
)
check_production(ENVIRONMENT, JWT_SECRET, DATABASE_URL)

# LLM planner on Groq. Without a key only the built-in rules can plan.
GROQ_API_KEY = (os.environ.get("OMNIAGENT_GROQ_API_KEY") or os.environ.get("GROQ_API_KEY") or "").strip()
GROQ_MODEL = os.environ.get("OMNIAGENT_GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_TIMEOUT_SECONDS = float(os.environ.get("OMNIAGENT_GROQ_TIMEOUT", "25"))
PLANS_PER_MINUTE = int(os.environ.get("OMNIAGENT_PLANS_PER_MINUTE", "20"))
# Plans below this confidence are flagged in the preview so the user looks twice.
LOW_CONFIDENCE = 0.6
