import os

# Must be set before the app (and its engine) is imported.
os.environ["OMNIAGENT_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
# Tests never reach the real the LLM API, whatever is in a local .env.
os.environ["OMNIAGENT_GROQ_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
