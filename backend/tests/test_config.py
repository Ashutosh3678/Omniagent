from __future__ import annotations

import pytest

from app.config import DEV_JWT_SECRET, check_production, normalize_database_url


@pytest.mark.parametrize(
    "given,expected",
    [
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///:memory:"),
    ],
)
def test_database_urls_get_the_driver_named(given: str, expected: str) -> None:
    assert normalize_database_url(given) == expected


GOOD_SECRET = "x" * 40
PG = "postgresql+psycopg://u:p@host/db"


def test_development_accepts_the_dev_defaults() -> None:
    check_production("development", DEV_JWT_SECRET, "sqlite+pysqlite:///:memory:")


def test_production_accepts_a_real_setup() -> None:
    check_production("production", GOOD_SECRET, PG)


@pytest.mark.parametrize("secret", [DEV_JWT_SECRET, "short", ""])
def test_production_refuses_a_weak_or_default_secret(secret: str) -> None:
    with pytest.raises(RuntimeError, match="OMNIAGENT_JWT_SECRET"):
        check_production("production", secret, PG)


def test_production_refuses_sqlite() -> None:
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        check_production("production", GOOD_SECRET, "sqlite+pysqlite:///x.db")
