"""Runtime settings. Tokens default to local-dev values only."""

from __future__ import annotations

import os

APP_TOKEN = os.environ.get("OMNIAGENT_APP_TOKEN", "dev-app-token")
AGENT_TOKEN = os.environ.get("OMNIAGENT_AGENT_TOKEN", "dev-agent-token")
TASK_TIMEOUT_SECONDS = float(os.environ.get("OMNIAGENT_TASK_TIMEOUT", "90"))
HOST = os.environ.get("OMNIAGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("OMNIAGENT_PORT", "8000"))
