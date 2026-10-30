import os

# Must be set before the app (and its engine) is imported.
os.environ["OMNIAGENT_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
# Tests never reach the real Gemini API, whatever is in a local .env.
os.environ["OMNIAGENT_GEMINI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
