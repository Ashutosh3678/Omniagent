import os

# Must be set before the app (and its engine) is imported.
os.environ["OMNIAGENT_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
