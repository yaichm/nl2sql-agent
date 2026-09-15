"""Database connections. Two roles, two functions."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from nl2sql_agent.config import get_settings


@contextmanager
def admin_connection() -> Iterator[psycopg.Connection]:
    """Owner role. Introspection, catalog, migrations."""
    with psycopg.connect(get_settings().admin_dsn) as conn:
        yield conn


@contextmanager
def readonly_connection() -> Iterator[psycopg.Connection]:
    """Read-only role. This is where generated SQL runs."""
    with psycopg.connect(get_settings().readonly_dsn) as conn:
        yield conn


def check_connections() -> None:
    """Verifies both roles respond and that the second one is properly locked down."""
    with admin_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")

    with readonly_connection() as conn, conn.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        row = cur.fetchone()
        if row is None or row[0] != "on":
            raise RuntimeError(
                "rôle lecture seule non bridé : "
                "ALTER ROLE ... SET default_transaction_read_only = on"
            )
